"""Gradio UIの定義とエントリーポイント

2ch/5chまとめ風ジェネレーターのメイン画面を構成し、
全処理パイプラインを接続する。
スレッドタブではリアルタイムに議論の様子を表示する。
"""

import asyncio
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

import gradio as gr

from src.agents.discussion import (
    build_discussion_agents,
    run_discussion_stream,
)
from src.agents.persona import Persona, generate_personas
from src.agents.summarizer import generate_thread_title, run_summarizer
from src.formatter.html_renderer import (
    render_matome_html,
    render_thread_footer,
    render_thread_header,
    render_thread_loading,
    render_thread_post,
)
from src.formatter.json_exporter import export_as_json
from src.formatter.text_exporter import export_as_text
from src.models.client_factory import load_settings
from src.utils.rate_limiter import RateLimiter

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import TextMessage

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


def _build_agent_persona_map(
    personas: list[Persona],
) -> dict[str, Persona]:
    """エージェント名→ペルソナの対応辞書を構築する"""
    mapping: dict[str, Persona] = {}
    for i, persona in enumerate(personas):
        mapping[f"agent_{i}_{persona.display_id}"] = persona
    return mapping


async def _generate_matome_streaming(
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
) -> Any:
    """まとめ生成の全パイプラインを非同期ストリーミングで実行する

    asyncジェネレーターとしてyieldし、
    外側の同期ラッパーがGradioに返す。

    Yields:
        (ステータス, スレッドHTML, まとめHTML, 生ログ, txtパス, jsonパス) のタプル
    """
    # 出力の初期値
    empty = ("", "", "", "", None, None)

    if not theme.strip():
        yield ("エラー: テーマを入力してください。", "", "", "", None, None)
        return

    settings = load_settings()
    rate_limiter = RateLimiter(wait_seconds=wait_time_sec)

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
        yield ("ペルソナを生成中...", "", "", "", None, None)
        personas = generate_personas(participant_count, tones)
        agent_map = _build_agent_persona_map(personas)

        # ステップ2: スレタイ生成
        yield ("スレッドタイトルを生成中...", "", "", "", None, None)
        if auto_title_flag:
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
            thread_title = manual_title.strip() if manual_title.strip() else f"【議論】{theme}"

        # ステップ3: 議論用エージェント構築
        yield ("議論用エージェントを構築中...", "", "", "", None, None)
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

        # ステップ4: 議論実行（ストリーミング）
        # スレッドHTMLをリアルタイムで構築
        thread_html = render_thread_header(thread_title)
        raw_log_lines: list[str] = []
        res_number = 0
        now_str = datetime.now().strftime("%Y/%m/%d(%a) %H:%M:%S")
        discussion_result: TaskResult | None = None

        # ストリーミングで議論を実行
        stream = run_discussion_stream(
            agents=agents,
            thread_title=thread_title,
            theme=f"{theme}\n\n{full_context}" if full_context else theme,
            conversation_count=conv_count,
        )

        async for item in stream:
            if isinstance(item, TaskResult):
                discussion_result = item
                continue

            if isinstance(item, TextMessage):
                res_number += 1
                source = item.source
                content = item.content

                # ペルソナ情報を取得
                persona = agent_map.get(source)
                if source == "user":
                    display_name = "1"
                    display_id = "Thread0P"
                elif persona:
                    display_name = persona.name
                    display_id = persona.display_id
                else:
                    display_name = "名無しさん"
                    display_id = source[-8:] if len(source) >= 8 else source

                # 日時文字列を少しランダム化（秒をレス番号で変える）
                post_time = datetime.now().strftime("%Y/%m/%d(%a) %H:%M:%S")

                # スレッドHTMLにレスを追加
                post_html = render_thread_post(
                    number=res_number,
                    name=display_name,
                    display_id=display_id,
                    date_str=post_time,
                    content=content,
                    is_new=True,
                )
                # ローディングインジケーター付きHTML
                loading = render_thread_loading(res_number, conv_count)
                current_thread_html = thread_html + post_html + loading + "\n  </div>\n</div>"

                # 生ログに追加
                raw_log_lines.append(f"[{source}]\n{content}\n")
                raw_log = "\n".join(raw_log_lines)

                # 途中経過をyield
                status = f"議論を実行中... ({res_number}/{conv_count}レス)"
                yield (status, current_thread_html, "", raw_log, None, None)

                # 次のレスのために蓄積
                thread_html += post_html

        # スレッド完了のフッターを追加
        thread_html += render_thread_footer(res_number)
        raw_log = "\n".join(raw_log_lines)

        # ステップ5: まとめ生成
        if discussion_result is None:
            yield ("エラー: 議論の結果が取得できませんでした。", thread_html, "", raw_log, None, None)
            return

        yield (
            "まとめ記事を生成中...",
            thread_html,
            "",
            raw_log,
            None,
            None,
        )

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

        comments_count = len(matome_data.get("thread_comments", []))
        status = f"完了！ {res_number}件のレスから{comments_count}件をピックアップしました。"
        yield (status, thread_html, matome_html, raw_log, str(txt_path), str(json_path))

    except RuntimeError as e:
        yield (f"設定エラー: {e}", "", "", "", None, None)
    except ConnectionError:
        yield (
            "接続エラー: ローカルサーバーに接続できません。"
            "Ollama/LM Studioが起動しているか確認してください。",
            "", "", "", None, None,
        )
    except Exception as e:
        tb = traceback.format_exc()
        yield (f"エラーが発生しました: {e}\n\n{tb}", "", "", "", None, None)


def generate_matome_sync(
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
) -> Generator[tuple[str, str, str, str, str | None, str | None], None, None]:
    """Gradioから呼ばれるジェネレーター関数（同期ラッパー）

    内部で非同期ストリーミング関数を実行し、
    yieldされた結果をそのまま返す。
    """
    async def _collect():
        """非同期ジェネレーターを同期的に実行し結果をリストに集める"""
        results = []
        async for item in _generate_matome_streaming(
            theme, context, tones, int(conv_count),
            int(participant_count), image_path, file_path,
            auto_title_flag, manual_title, disc_provider,
            disc_model, sum_provider, sum_model, wait_time_sec,
            ollama_url, lmstudio_url,
        ):
            results.append(item)
        return results

    # 新しいイベントループで実行
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Gradio内部のイベントループが動いている場合
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, _collect())
            results = future.result()
    else:
        results = asyncio.run(_collect())

    for item in results:
        yield item


def toggle_manual_title(auto_flag: bool) -> dict:
    """スレタイ自動生成チェックボックスの状態に応じて手動入力欄の表示を切り替える"""
    return gr.update(visible=not auto_flag)


# GradioのカスタムCSS
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
        "まとめサイト風に自動編集します。「スレッド」タブで議論の進行をリアルタイムに見られます。"
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
                with gr.TabItem("スレッド"):
                    thread_output = gr.HTML(
                        label="スレッド表示（リアルタイム）",
                    )
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
        fn=generate_matome_sync,
        inputs=[
            theme_input, context_input, tone_input, conv_count,
            participant_count, image_input, file_input, auto_title,
            manual_title, disc_provider, disc_model, sum_provider,
            sum_model, wait_time, ollama_url, lmstudio_url,
        ],
        outputs=[
            status_text, thread_output, html_output, raw_log,
            txt_download, json_download,
        ],
    )

# エントリーポイント
if __name__ == "__main__":
    app.launch(server_name="127.0.0.1")
