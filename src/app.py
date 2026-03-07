"""Gradio UIの定義とエントリーポイント

2ch/5chまとめ風ジェネレーターのメイン画面を構成し、
全処理パイプラインを接続する。
スレッドタブではリアルタイムに議論の様子を表示する。
生成完了後、9ファイル（3種類×3形式）をZIPにまとめてダウンロードできる。
"""

import traceback
import zipfile
from datetime import datetime
from pathlib import Path

import gradio as gr

from src.agents.discussion import (
    build_discussion_agents,
    run_discussion_stream,
)
from src.agents.persona import Persona, generate_personas
from src.agents.summarizer import generate_thread_title, run_summarizer
from src.formatter.html_renderer import (
    export_matome_as_html,
    export_rawlog_as_html,
    export_thread_as_html,
    render_matome_html,
    render_thread_footer,
    render_thread_header,
    render_thread_loading,
    render_thread_post,
)
from src.formatter.json_exporter import (
    export_matome_as_json,
    export_rawlog_as_json,
    export_thread_as_json,
)
from src.formatter.text_exporter import (
    export_matome_as_text,
    export_rawlog_as_text,
    export_thread_as_text,
)
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


def _create_zip(file_paths: list[Path], zip_path: Path) -> Path:
    """複数ファイルをZIPにまとめる"""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in file_paths:
            if fp.exists():
                zf.write(fp, fp.name)
    return zip_path


async def generate_matome_streaming(
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
):
    """まとめ生成の全パイプライン（非同期ジェネレーター）

    Yields:
        (ステータス, スレッドHTML, まとめHTML, 生ログ, ZIPパス)
    """
    conv_count = int(conv_count)
    participant_count = int(participant_count)

    if not theme.strip():
        yield ("エラー: テーマを入力してください。", "", "", "", None)
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
        yield ("ペルソナを生成中...", "", "", "", None)
        personas = generate_personas(participant_count, tones)
        agent_map = _build_agent_persona_map(personas)

        # ステップ2: スレタイ生成
        yield ("スレッドタイトルを生成中...", "", "", "", None)
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
            thread_title = (
                manual_title.strip() if manual_title.strip()
                else f"【議論】{theme}"
            )

        # ステップ3: 議論用エージェント構築
        yield ("議論用エージェントを構築中...", "", "", "", None)
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
        thread_html_parts = render_thread_header(thread_title)
        raw_log_lines: list[str] = []
        # エクスポート用の構造化データ
        thread_posts_data: list[dict[str, Any]] = []
        raw_log_entries: list[dict[str, str]] = []

        res_number = 0
        discussion_result: TaskResult | None = None

        stream = run_discussion_stream(
            agents=agents,
            thread_title=thread_title,
            theme=(
                f"{theme}\n\n{full_context}" if full_context else theme
            ),
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
                    display_id = (
                        source[-8:] if len(source) >= 8 else source
                    )

                post_time = datetime.now().strftime(
                    "%Y/%m/%d(%a) %H:%M:%S"
                )

                # エクスポート用データに追加
                thread_posts_data.append({
                    "number": res_number,
                    "name": display_name,
                    "display_id": display_id,
                    "date_str": post_time,
                    "content": content,
                })
                raw_log_entries.append({
                    "source": source,
                    "content": content,
                })

                # スレッドHTMLにレスを追加
                post_html = render_thread_post(
                    number=res_number,
                    name=display_name,
                    display_id=display_id,
                    date_str=post_time,
                    content=content,
                    is_new=True,
                )
                loading = render_thread_loading(
                    res_number, conv_count
                )
                display_html = (
                    thread_html_parts + post_html + loading
                    + "\n  </div>\n</div>"
                )

                raw_log_lines.append(f"[{source}]\n{content}\n")
                raw_log = "\n".join(raw_log_lines)

                status = (
                    f"議論を実行中... ({res_number}/{conv_count}レス)"
                )
                yield (status, display_html, "", raw_log, None)

                thread_html_parts += post_html

        # スレッド完了
        thread_html_final = thread_html_parts + render_thread_footer(
            res_number
        )
        raw_log = "\n".join(raw_log_lines)

        if discussion_result is None:
            yield (
                "エラー: 議論の結果が取得できませんでした。",
                thread_html_final, "", raw_log, None,
            )
            return

        # ステップ5: まとめ生成
        yield (
            "まとめ記事を生成中...",
            thread_html_final, "", raw_log, None,
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
        yield (
            "ファイルを生成中...",
            thread_html_final, "", raw_log, None,
        )

        matome_html = render_matome_html(matome_data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 9ファイルを生成
        export_files: list[Path] = []

        # まとめ × 3形式
        p = OUTPUT_DIR / f"matome_{timestamp}.txt"
        export_matome_as_text(matome_data, p)
        export_files.append(p)

        p = OUTPUT_DIR / f"matome_{timestamp}.json"
        export_matome_as_json(matome_data, p)
        export_files.append(p)

        p = OUTPUT_DIR / f"matome_{timestamp}.html"
        export_matome_as_html(matome_data, p)
        export_files.append(p)

        # スレッド × 3形式
        p = OUTPUT_DIR / f"thread_{timestamp}.txt"
        export_thread_as_text(thread_posts_data, thread_title, p)
        export_files.append(p)

        p = OUTPUT_DIR / f"thread_{timestamp}.json"
        export_thread_as_json(thread_posts_data, thread_title, p)
        export_files.append(p)

        p = OUTPUT_DIR / f"thread_{timestamp}.html"
        export_thread_as_html(
            thread_posts_data, thread_title, res_number, p
        )
        export_files.append(p)

        # 生ログ × 3形式
        p = OUTPUT_DIR / f"rawlog_{timestamp}.txt"
        export_rawlog_as_text(raw_log_lines, p)
        export_files.append(p)

        p = OUTPUT_DIR / f"rawlog_{timestamp}.json"
        export_rawlog_as_json(raw_log_entries, p)
        export_files.append(p)

        p = OUTPUT_DIR / f"rawlog_{timestamp}.html"
        export_rawlog_as_html(raw_log_entries, p)
        export_files.append(p)

        # ZIP作成
        zip_path = OUTPUT_DIR / f"matome_all_{timestamp}.zip"
        _create_zip(export_files, zip_path)

        # クライアントクローズ
        for agent in agents:
            try:
                await agent._inner_agent._model_client.close()
            except Exception:
                pass

        comments_count = len(matome_data.get("thread_comments", []))
        status = (
            f"完了！ {res_number}件のレスから"
            f"{comments_count}件をピックアップしました。"
        )
        yield (
            status, thread_html_final, matome_html, raw_log,
            str(zip_path),
        )

    except RuntimeError as e:
        yield (f"設定エラー: {e}", "", "", "", None)
    except ConnectionError:
        yield (
            "接続エラー: ローカルサーバーに接続できません。"
            "Ollama/LM Studioが起動しているか確認してください。",
            "", "", "", None,
        )
    except Exception as e:
        tb = traceback.format_exc()
        yield (
            f"エラーが発生しました: {e}\n\n{tb}",
            "", "", "", None,
        )


def toggle_manual_title(auto_flag: bool) -> dict:
    """スレタイ自動生成チェックの状態に応じて手動入力欄を切り替える"""
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
        "まとめサイト風に自動編集します。"
        "「スレッド」タブで議論の進行をリアルタイムに見られます。"
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
                placeholder=(
                    "例: 最終回は賛否両論だった。"
                    "作画は神だったけどストーリーが…"
                ),
            )
            tone_input = gr.CheckboxGroup(
                choices=[
                    "通常", "白熱", "煽り", "賛成多め",
                    "批判的", "ネタ・ボケ", "懐古厨",
                    "にわか vs 古参",
                ],
                value=["通常"],
                label="議論のトーン（複数選択可）",
            )
            conv_count = gr.Slider(
                minimum=5, maximum=100, value=20, step=5,
                label="会話数",
                info=(
                    "会話数が多いほどAPIコストと生成時間が増加します"
                ),
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
                    choices=[
                        "openai", "gemini", "ollama", "lmstudio",
                    ],
                    value="gemini",
                    label="議論用LLMプロバイダー",
                )
                disc_model = gr.Textbox(
                    value="gemini-3.1-flash-lite-preview",
                    label="議論用モデル名",
                )
                sum_provider = gr.Dropdown(
                    choices=[
                        "openai", "gemini", "ollama", "lmstudio",
                    ],
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
                    info=(
                        "リクエスト間の待機時間。"
                        "レートリミットエラーが出る場合は増やしてください"
                    ),
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
                placeholder=(
                    "「まとめを生成する」を押すと処理が始まります"
                ),
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

            gr.Markdown(
                "### 一括ダウンロード\n"
                "スレッド・まとめ・生ログの各データを "
                "`.txt` / `.json` / `.html` の9ファイルに書き出し、"
                "ZIPにまとめてダウンロードできます。"
            )
            zip_download = gr.File(
                label="全データ一括ダウンロード（ZIP）",
            )

    # 生成ボタンのクリックイベント
    generate_btn.click(
        fn=generate_matome_streaming,
        inputs=[
            theme_input, context_input, tone_input, conv_count,
            participant_count, image_input, file_input, auto_title,
            manual_title, disc_provider, disc_model, sum_provider,
            sum_model, wait_time, ollama_url, lmstudio_url,
        ],
        outputs=[
            status_text, thread_output, html_output, raw_log,
            zip_download,
        ],
    )

# エントリーポイント
if __name__ == "__main__":
    app.launch(server_name="127.0.0.1")
