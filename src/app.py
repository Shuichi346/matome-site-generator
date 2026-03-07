"""Gradio UIの定義とエントリーポイント

2ch/5chまとめ風ジェネレーターのメイン画面を構成し、
全処理パイプラインを接続する。
"""

import asyncio
import base64
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import gradio as gr

from src.agents.discussion import build_discussion_agents, run_discussion
from src.agents.persona import generate_personas
from src.agents.summarizer import generate_thread_title, run_summarizer
from src.formatter.html_renderer import render_matome_html
from src.formatter.json_exporter import export_as_json
from src.formatter.text_exporter import export_as_text
from src.models.client_factory import load_settings
from src.utils.rate_limiter import RateLimiter

# 出力ディレクトリ
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def _read_attached_file(file_path: str | None) -> str:
    """添付ファイルの内容を読み込む"""
    if not file_path:
        return ""
    try:
        path = Path(file_path)
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _encode_image(image_path: str | None) -> str:
    """添付画像の情報をテキスト化する"""
    if not image_path:
        return ""
    return f"（参考画像が添付されています: {Path(image_path).name}）"


async def _generate_matome_async(
    theme: str,
    context: str,
    tones: list[str],
    conv_count: int,
    participant_count: int,
    image_path: str | None,
    file_path: str | None,
    auto_title_flag: bool,
    manual_title: str,
    disc_provider: str,
    disc_model: str,
    sum_provider: str,
    sum_model: str,
    wait_time_sec: float,
    ollama_url: str,
    lmstudio_url: str,
    progress_callback: Any = None,
) -> tuple[str, str, str, str | None, str | None]:
    """まとめ生成の全パイプラインを非同期で実行する

    Returns:
        (ステータス, HTML, 生ログ, txtファイルパス, jsonファイルパス)
    """
    # 入力バリデーション
    if not theme.strip():
        return ("エラー: テーマを入力してください。", "", "", None, None)

    settings = load_settings()
    rate_limiter = RateLimiter(wait_seconds=wait_time_sec)
    conv_count = int(conv_count)
    participant_count = int(participant_count)

    # 添付ファイルの内容を補足情報に追加
    extra_context = ""
    file_content = _read_attached_file(file_path)
    if file_content:
        extra_context += f"\n【添付ファイルの内容】\n{file_content[:2000]}"
    image_info = _encode_image(image_path)
    if image_info:
        extra_context += f"\n{image_info}"

    full_context = context + extra_context

    try:
        # ステップ1: ペルソナ生成
        status = "ペルソナを生成中..."
        personas = generate_personas(participant_count, tones)

        # ステップ2: スレタイ生成
        if auto_title_flag:
            status = "スレッドタイトルを生成中..."
            thread_title = await generate_thread_title(
                theme=theme,
                provider=sum_provider,
                model_name=sum_model,
                rate_limiter=rate_limiter,
                settings=settings,
                ollama_url=ollama_url,
                lmstudio_url=lmstudio_url,
            )
        else:
            thread_title = manual_title if manual_title.strip() else f"【議論】{theme}"

        # ステップ3: 議論用エージェント構築
        status = "議論用エージェントを構築中..."
        agents = build_discussion_agents(
            personas=personas,
            theme=theme,
            context=full_context,
            tones=tones,
            provider=disc_provider,
            model_name=disc_model,
            rate_limiter=rate_limiter,
            settings=settings,
            ollama_url=ollama_url,
            lmstudio_url=lmstudio_url,
        )

        # ステップ4: 議論実行
        status = f"議論を実行中... (0/{conv_count}レス)"
        discussion_result = await run_discussion(
            agents=agents,
            thread_title=thread_title,
            theme=f"{theme}\n\n{full_context}" if full_context else theme,
            conversation_count=conv_count,
        )

        # 議論の生ログ生成
        raw_log_lines: list[str] = []
        from autogen_agentchat.messages import TextMessage as TM
        for msg in discussion_result.messages:
            if isinstance(msg, TM):
                raw_log_lines.append(f"[{msg.source}]\n{msg.content}\n")
        raw_log = "\n".join(raw_log_lines)

        # ステップ5: まとめ生成
        status = "まとめ記事を生成中..."
        matome_data = await run_summarizer(
            discussion_result=discussion_result,
            personas=personas,
            provider=sum_provider,
            model_name=sum_model,
            rate_limiter=rate_limiter,
            settings=settings,
            ollama_url=ollama_url,
            lmstudio_url=lmstudio_url,
        )

        # ステップ6: 出力生成
        status = "出力ファイルを生成中..."
        matome_html = render_matome_html(matome_data)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        txt_path = OUTPUT_DIR / f"matome_{timestamp}.txt"
        json_path = OUTPUT_DIR / f"matome_{timestamp}.json"

        export_as_text(matome_data, txt_path)
        export_as_json(matome_data, json_path)

        # エージェントのクライアントをクローズ
        for agent in agents:
            try:
                await agent._inner_agent._model_client.close()
            except Exception:
                pass

        status = f"完了！ {len(discussion_result.messages)}件のメッセージから{len(matome_data.get('thread_comments', []))}件をピックアップしました。"
        return (status, matome_html, raw_log, str(txt_path), str(json_path))

    except RuntimeError as e:
        return (f"設定エラー: {e}", "", "", None, None)
    except ConnectionError:
        return (
            "接続エラー: ローカルサーバーに接続できません。"
            "Ollama/LM Studioが起動しているか確認してください。",
            "", "", None, None,
        )
    except Exception as e:
        tb = traceback.format_exc()
        return (f"エラーが発生しました: {e}\n\n{tb}", "", "", None, None)


def generate_matome(
    theme: str,
    context: str,
    tones: list[str],
    conv_count: float,
    participant_count: float,
    image_path: str | None,
    file_path: str | None,
    auto_title_flag: bool,
    manual_title: str,
    disc_provider: str,
    disc_model: str,
    sum_provider: str,
    sum_model: str,
    wait_time_sec: float,
    ollama_url: str,
    lmstudio_url: str,
) -> tuple[str, str, str, str | None, str | None]:
    """Gradioから呼ばれるメイン処理関数（同期ラッパー）"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Gradioがすでにイベントループを持っている場合は
            # nest_asyncioパターンではなく、新規スレッドで実行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    _generate_matome_async(
                        theme, context, tones, int(conv_count),
                        int(participant_count), image_path, file_path,
                        auto_title_flag, manual_title, disc_provider,
                        disc_model, sum_provider, sum_model, wait_time_sec,
                        ollama_url, lmstudio_url,
                    ),
                )
                return future.result()
    except RuntimeError:
        pass

    return asyncio.run(
        _generate_matome_async(
            theme, context, tones, int(conv_count),
            int(participant_count), image_path, file_path,
            auto_title_flag, manual_title, disc_provider,
            disc_model, sum_provider, sum_model, wait_time_sec,
            ollama_url, lmstudio_url,
        )
    )


def toggle_manual_title(auto_flag: bool) -> dict:
    """スレタイ自動生成チェックボックスの状態に応じて手動入力欄の表示を切り替える"""
    return gr.update(visible=not auto_flag)


# GradioのカスタムCSS（アプリ全体のスタイル調整）
CUSTOM_CSS = """
.gradio-container {
    max-width: 1200px !important;
}
"""

# Gradio UIの構築
with gr.Blocks(
    title="2ch/5chまとめ風ジェネレーター",
    css=CUSTOM_CSS,
) as app:
    gr.Markdown("# 2ch/5chまとめ風ジェネレーター")
    gr.Markdown(
        "テーマを入力すると、複数のAIエージェントが2ちゃんねらー風に議論を行い、"
        "まとめサイト風に自動編集します。"
    )

    with gr.Row():
        # === 左カラム: 入力エリア ===
        with gr.Column(scale=1):
            theme_input = gr.Textbox(
                label="テーマ",
                lines=3,
                placeholder="例: 推しの子 最終回の感想",
            )
            context_input = gr.Textbox(
                label="議論の方向性・補足",
                lines=3,
                placeholder="例: 最終回は賛否両論だった。作画は神だったけどストーリーが…",
            )
            tone_input = gr.CheckboxGroup(
                choices=[
                    "通常", "白熱", "煽り", "賛成多め",
                    "批判的", "ネタ・ボケ", "懐古厨", "にわか vs 古参",
                ],
                value=["通常"],
                label="議論のトーン（複数選択可）",
            )
            conv_count = gr.Slider(
                minimum=5, maximum=100, value=20, step=5,
                label="会話数",
                info="会話数が多いほどAPIコストと生成時間が増加します",
            )
            participant_count = gr.Slider(
                minimum=2, maximum=10, value=5, step=1,
                label="参加人数",
            )
            image_input = gr.Image(
                label="参考画像（任意）",
                type="filepath",
            )
            file_input = gr.File(label="参考ファイル（任意）")

            auto_title = gr.Checkbox(
                value=True,
                label="スレッドタイトルをAIが自動生成",
            )
            manual_title = gr.Textbox(
                label="手動スレッドタイトル",
                visible=False,
                placeholder="スレッドタイトルを入力...",
            )

            # チェックボックス切り替えで手動入力欄を表示/非表示
            auto_title.change(
                fn=toggle_manual_title,
                inputs=[auto_title],
                outputs=[manual_title],
            )

            with gr.Accordion("詳細設定", open=False):
                disc_provider = gr.Dropdown(
                    choices=["openai", "gemini", "ollama", "lmstudio"],
                    value="gemini",
                    label="議論用LLMプロバイダー",
                )
                disc_model = gr.Textbox(
                    value="gemini-3.1-flash-lite-preview",
                    label="議論用モデル名",
                )
                sum_provider = gr.Dropdown(
                    choices=["openai", "gemini", "ollama", "lmstudio"],
                    value="gemini",
                    label="まとめ用LLMプロバイダー",
                )
                sum_model = gr.Textbox(
                    value="gemini-3-flash-preview",
                    label="まとめ用モデル名",
                )
                wait_time = gr.Slider(
                    minimum=0.0, maximum=10.0, value=1.0, step=0.5,
                    label="APIウェイトタイム（秒）",
                    info="リクエスト間の待機時間。レートリミットエラーが出る場合は増やしてください",
                )
                ollama_url = gr.Textbox(
                    value="http://localhost:11434",
                    label="Ollama サーバーURL",
                )
                lmstudio_url = gr.Textbox(
                    value="http://localhost:1234/v1",
                    label="LM Studio サーバーURL",
                )

            generate_btn = gr.Button(
                "まとめを生成する",
                variant="primary",
                size="lg",
            )

        # === 右カラム: 出力エリア ===
        with gr.Column(scale=2):
            status_text = gr.Textbox(
                label="ステータス",
                interactive=False,
                placeholder="「まとめを生成する」を押すと処理が始まります",
            )

            with gr.Tabs():
                with gr.TabItem("まとめ表示"):
                    html_output = gr.HTML(label="まとめ風表示")
                with gr.TabItem("生ログ"):
                    raw_log = gr.Textbox(
                        label="議論の生ログ",
                        lines=20,
                        interactive=False,
                    )

            with gr.Row():
                txt_download = gr.File(label="テキスト(.txt)ダウンロード")
                json_download = gr.File(label="JSON(.json)ダウンロード")

    # 生成ボタンのクリックイベント
    generate_btn.click(
        fn=generate_matome,
        inputs=[
            theme_input, context_input, tone_input, conv_count,
            participant_count, image_input, file_input, auto_title,
            manual_title, disc_provider, disc_model, sum_provider,
            sum_model, wait_time, ollama_url, lmstudio_url,
        ],
        outputs=[
            status_text, html_output, raw_log,
            txt_download, json_download,
        ],
    )

# エントリーポイント
if __name__ == "__main__":
    app.launch(server_name="127.0.0.1")
