"""Gradio UIの定義とエントリーポイント

2ch/5chまとめ風ジェネレーターのメイン画面を構成し、
全処理パイプラインを接続する。
スレッドタブではリアルタイムに議論の様子を表示する。
生成完了後、9ファイル（3種類×3形式）をZIPにまとめてダウンロードできる。
URL参照・Web検索によるコンテキスト補強に対応。
スレッド表示では参考情報や内部指示は非表示にし、
テーマと方向性のみを簡潔に表示する。
OpenRouter / カスタムOpenAI互換プロバイダーに対応。
レートリミットエラー発生時はユーザーに通知して停止する。
詳細設定は専用タブに分離し、UI設定はJSONで保存・復元する。
プロバイダーごとのモデル名を記憶し、切り替え時に自動復元する。
"""

import json
import re
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import gradio as gr

from src.agents.discussion import (
    RateLimitError,
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
from src.models.client_factory import ALL_PROVIDERS, load_settings
from src.utils.rate_limiter import RateLimiter
from src.utils.web_fetcher import (
    fetch_multiple_urls,
    format_search_results_as_context,
    format_url_results_as_context,
    search_web,
)

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import TextMessage

# 出力ディレクトリ
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# UI設定ファイルのパス
UI_SETTINGS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "ui_settings.json"
)

# URLを検出する正規表現
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"'`\])},;]+"
)

# プロバイダーごとのデフォルトモデル名
_DEFAULT_PROVIDER_MODELS: dict[str, str] = {
    "openai": "gpt-5-mini",
    "gemini": "gemini-3.1-flash-lite-preview",
    "ollama": "qwen3.5",
    "lmstudio": "local-model",
    "openrouter": "stepfun/step-3.5-flash:free",
    "custom_openai": "model-name",
}

# まとめ用のデフォルト（より高品質なモデル推奨）
_DEFAULT_SUM_PROVIDER_MODELS: dict[str, str] = {
    "openai": "gpt-5.4",
    "gemini": "gemini-3-flash-preview",
    "ollama": "qwen3.5",
    "lmstudio": "local-model",
    "openrouter": "stepfun/step-3.5-flash:free",
    "custom_openai": "model-name",
}

# UI設定のデフォルト値
_DEFAULT_UI_SETTINGS: dict[str, Any] = {
    "tone": ["通常"],
    "conv_count": 20,
    "participant_count": 5,
    "auto_title": True,
    "disc_provider": "gemini",
    "disc_model": "gemini-3.1-flash-lite-preview",
    "sum_provider": "gemini",
    "sum_model": "gemini-3-flash-preview",
    "wait_time": 1.0,
    "ollama_url": "http://localhost:11434",
    "lmstudio_url": "http://localhost:1234/v1",
    "openrouter_url": "https://openrouter.ai/api/v1",
    "custom_openai_url": "",
    "custom_openai_api_key": "",
    "disc_provider_models": dict(_DEFAULT_PROVIDER_MODELS),
    "sum_provider_models": dict(_DEFAULT_SUM_PROVIDER_MODELS),
}


def _load_ui_settings() -> dict[str, Any]:
    """UI設定をJSONファイルから読み込む

    ファイルが存在しない場合やパースに失敗した場合は
    デフォルト値を返す。プロバイダー→モデルのマッピングは
    デフォルトをベースに保存値で上書きする。
    """
    settings = json.loads(json.dumps(_DEFAULT_UI_SETTINGS))
    if UI_SETTINGS_PATH.exists():
        try:
            with open(UI_SETTINGS_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                # プロバイダーモデルマッピングはマージで扱う
                for key in ("disc_provider_models", "sum_provider_models"):
                    if key in saved and isinstance(saved[key], dict):
                        settings[key].update(saved[key])
                        del saved[key]
                settings.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def _save_ui_settings(settings: dict[str, Any]) -> None:
    """UI設定をJSONファイルに保存する"""
    UI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(UI_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


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


def _extract_urls(text: str) -> list[str]:
    """テキストからURLを抽出する"""
    return _URL_PATTERN.findall(text)


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


def _build_display_text(theme: str, context: str) -> str:
    """スレッド >>1 に表示する短いテキストを組み立てる"""
    parts: list[str] = []
    theme_clean = _URL_PATTERN.sub("", theme).strip()
    if theme_clean:
        parts.append(theme_clean)
    context_clean = _URL_PATTERN.sub("", context).strip()
    if context_clean:
        parts.append(context_clean)
    if not parts:
        return "（テーマ未設定）"
    text = "\n".join(parts)
    if len(text) > 200:
        text = text[:200] + "…"
    return text


def _render_rate_limit_notice(message: str) -> str:
    """レートリミットエラーのHTML通知を生成する"""
    notice_style = (
        "margin:12px 8px;padding:16px 20px;"
        "background:#fff3cd;border:2px solid #ffc107;"
        "border-radius:8px;font-size:0.95em;"
        "color:#856404;line-height:1.6;"
    )
    icon_style = "font-size:1.3em;margin-right:8px;"
    title_style = "font-weight:bold;font-size:1.05em;margin-bottom:8px;"
    hint_style = (
        "margin-top:10px;padding-top:10px;"
        "border-top:1px solid #ffeeba;font-size:0.88em;color:#866d1a;"
    )
    return f"""
    <div style="{notice_style}">
      <div style="{title_style}">
        <span style="{icon_style}">&#9888;</span>
        APIレートリミットに達しました
      </div>
      <div>{message}</div>
      <div style="{hint_style}">
        &#128161; 対処法：「APIウェイトタイム」を増やす（3〜5秒推奨）／
        しばらく待ってから再試行する／
        無料モデルの場合は有料プランまたは別モデルを検討する
      </div>
    </div>"""


# ========================================
# プロバイダー切替時のモデル名自動復元
# ========================================

def on_disc_provider_change(
    new_provider: str,
    current_model: str,
    mapping: dict[str, str],
) -> tuple[str, dict[str, str]]:
    """議論用プロバイダーが変更された時にモデル名を復元する

    Returns:
        (新しいモデル名, 更新後のマッピング)
    """
    restored = mapping.get(
        new_provider,
        _DEFAULT_PROVIDER_MODELS.get(new_provider, ""),
    )
    return restored, mapping


def on_disc_model_change(
    provider: str,
    new_model: str,
    mapping: dict[str, str],
) -> dict[str, str]:
    """議論用モデル名が手動変更された時にマッピングを更新する

    Returns:
        更新後のマッピング
    """
    if new_model.strip():
        mapping[provider] = new_model.strip()
    return mapping


def on_sum_provider_change(
    new_provider: str,
    current_model: str,
    mapping: dict[str, str],
) -> tuple[str, dict[str, str]]:
    """まとめ用プロバイダーが変更された時にモデル名を復元する

    Returns:
        (新しいモデル名, 更新後のマッピング)
    """
    restored = mapping.get(
        new_provider,
        _DEFAULT_SUM_PROVIDER_MODELS.get(new_provider, ""),
    )
    return restored, mapping


def on_sum_model_change(
    provider: str,
    new_model: str,
    mapping: dict[str, str],
) -> dict[str, str]:
    """まとめ用モデル名が手動変更された時にマッピングを更新する

    Returns:
        更新後のマッピング
    """
    if new_model.strip():
        mapping[provider] = new_model.strip()
    return mapping


# ========================================
# メイン生成処理
# ========================================

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
    openrouter_url: str,
    custom_openai_url: str,
    custom_openai_api_key: str,
    ref_urls: str,
    search_keywords: str,
    disc_mapping: dict[str, str],
    sum_mapping: dict[str, str],
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

    # 生成開始時にUI設定を保存する
    _save_ui_settings({
        "tone": tones,
        "conv_count": conv_count,
        "participant_count": participant_count,
        "auto_title": auto_title_flag,
        "disc_provider": disc_provider,
        "disc_model": disc_model,
        "sum_provider": sum_provider,
        "sum_model": sum_model,
        "wait_time": wait_time_sec,
        "ollama_url": ollama_url,
        "lmstudio_url": lmstudio_url,
        "openrouter_url": openrouter_url,
        "custom_openai_url": custom_openai_url,
        "custom_openai_api_key": custom_openai_api_key,
        "disc_provider_models": disc_mapping,
        "sum_provider_models": sum_mapping,
    })

    settings = load_settings()
    rate_limiter = RateLimiter(wait_seconds=wait_time_sec)

    # 添付ファイルの内容を補足情報に追加（LLMのみ参照、表示しない）
    extra_context = ""
    file_content = _read_attached_file(file_path)
    if file_content:
        extra_context += f"\n【添付ファイルの内容】\n{file_content[:2000]}"
    image_info = _encode_image(image_path)
    if image_info:
        extra_context += f"\n{image_info}"

    # URL参照
    all_urls: list[str] = []
    all_urls.extend(_extract_urls(theme))
    all_urls.extend(_extract_urls(context))
    if ref_urls.strip():
        for line in ref_urls.strip().splitlines():
            line = line.strip()
            if line:
                found = _extract_urls(line)
                all_urls.extend(found if found else [])
    seen: set[str] = set()
    unique_urls: list[str] = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    if unique_urls:
        yield (
            f"参考URLを取得中... ({len(unique_urls)}件)",
            "", "", "", None,
        )
        url_results = await fetch_multiple_urls(unique_urls)
        url_context = format_url_results_as_context(url_results)
        extra_context += url_context

    # Web検索
    if search_keywords.strip():
        yield (
            f"「{search_keywords.strip()}」でWeb検索中...",
            "", "", "", None,
        )
        search_results = await search_web(
            search_keywords.strip(), max_results=5
        )
        search_context = format_search_results_as_context(
            search_results
        )
        extra_context += search_context

    full_context = context + extra_context
    display_text = _build_display_text(theme, context)

    # プロバイダー固有のURL引数をまとめる
    provider_kwargs = {
        "ollama_url": ollama_url,
        "lmstudio_url": lmstudio_url,
        "openrouter_url": openrouter_url,
        "custom_openai_url": custom_openai_url,
        "custom_openai_api_key": custom_openai_api_key,
    }

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
                **provider_kwargs,
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
            **provider_kwargs,
        )

        # ステップ4: 議論実行（ストリーミング）
        thread_html_parts = render_thread_header(thread_title)
        raw_log_lines: list[str] = []
        thread_posts_data: list[dict[str, Any]] = []
        raw_log_entries: list[dict[str, str]] = []

        res_number = 0
        discussion_result: TaskResult | None = None
        rate_limit_hit = False

        try:
            stream = run_discussion_stream(
                agents=agents,
                thread_title=thread_title,
                theme=(
                    f"{theme}\n\n{full_context}"
                    if full_context else theme
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

                    persona = agent_map.get(source)

                    if source == "user":
                        display_name = "スレ主"
                        display_id = "Thread0P"
                        display_content = display_text
                    elif persona:
                        display_name = persona.name
                        display_id = persona.display_id
                        display_content = content
                    else:
                        display_name = "名無しさん"
                        display_id = (
                            source[-8:]
                            if len(source) >= 8 else source
                        )
                        display_content = content

                    post_time = datetime.now().strftime(
                        "%Y/%m/%d(%a) %H:%M:%S"
                    )

                    thread_posts_data.append({
                        "number": res_number,
                        "name": display_name,
                        "display_id": display_id,
                        "date_str": post_time,
                        "content": display_content,
                    })
                    raw_log_entries.append({
                        "source": source,
                        "content": content,
                    })

                    post_html = render_thread_post(
                        number=res_number,
                        name=display_name,
                        display_id=display_id,
                        date_str=post_time,
                        content=display_content,
                        is_new=True,
                    )
                    loading = render_thread_loading(
                        res_number, conv_count
                    )
                    display_html = (
                        thread_html_parts + post_html + loading
                        + "\n  </div>\n</div>"
                    )

                    raw_log_lines.append(
                        f"[{source}]\n{content}\n"
                    )
                    raw_log = "\n".join(raw_log_lines)

                    status = (
                        f"議論を実行中... "
                        f"({res_number}/{conv_count}レス)"
                    )
                    yield (
                        status, display_html, "", raw_log, None,
                    )

                    thread_html_parts += post_html

        except RateLimitError as e:
            rate_limit_hit = True
            rate_limit_msg = str(e)
            notice_html = _render_rate_limit_notice(rate_limit_msg)
            thread_html_parts += notice_html

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RateLimit" in err_str:
                rate_limit_hit = True
                rate_limit_msg = (
                    f"APIレートリミットに達しました: {err_str}"
                )
                notice_html = _render_rate_limit_notice(
                    rate_limit_msg
                )
                thread_html_parts += notice_html
            else:
                raise

        # スレッドHTML確定
        raw_log = "\n".join(raw_log_lines)
        if rate_limit_hit:
            thread_html_final = (
                thread_html_parts
                + render_thread_footer(res_number)
            )
            status_msg = (
                f"レートリミットにより停止しました"
                f"（{res_number}/{conv_count}レスで中断）。"
                f"ウェイトタイムを増やすか、"
                f"しばらく待ってから再試行してください。"
            )
            yield (
                status_msg, thread_html_final, "", raw_log, None,
            )
            return

        thread_html_final = (
            thread_html_parts + render_thread_footer(res_number)
        )

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

        try:
            matome_data = await run_summarizer(
                discussion_result=discussion_result,
                personas=personas,
                provider=sum_provider,
                model_name=sum_model,
                rate_limiter=rate_limiter,
                settings=settings,
                **provider_kwargs,
            )
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RateLimit" in err_str:
                yield (
                    f"まとめ生成中にレートリミットに達しました。"
                    f"ウェイトタイムを増やして再試行してください。"
                    f"\n詳細: {err_str}",
                    thread_html_final, "", raw_log, None,
                )
                return
            raise

        # ステップ6: 出力生成
        yield (
            "ファイルを生成中...",
            thread_html_final, "", raw_log, None,
        )

        matome_html = render_matome_html(matome_data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        export_files: list[Path] = []

        p = OUTPUT_DIR / f"matome_{timestamp}.txt"
        export_matome_as_text(matome_data, p)
        export_files.append(p)

        p = OUTPUT_DIR / f"matome_{timestamp}.json"
        export_matome_as_json(matome_data, p)
        export_files.append(p)

        p = OUTPUT_DIR / f"matome_{timestamp}.html"
        export_matome_as_html(matome_data, p)
        export_files.append(p)

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

        p = OUTPUT_DIR / f"rawlog_{timestamp}.txt"
        export_rawlog_as_text(raw_log_lines, p)
        export_files.append(p)

        p = OUTPUT_DIR / f"rawlog_{timestamp}.json"
        export_rawlog_as_json(raw_log_entries, p)
        export_files.append(p)

        p = OUTPUT_DIR / f"rawlog_{timestamp}.html"
        export_rawlog_as_html(raw_log_entries, p)
        export_files.append(p)

        zip_path = OUTPUT_DIR / f"matome_all_{timestamp}.zip"
        _create_zip(export_files, zip_path)

        for agent in agents:
            try:
                await agent._inner_agent._model_client.close()
            except Exception:
                pass

        comments_count = len(
            matome_data.get("thread_comments", [])
        )
        status = (
            f"完了！ {res_number}件のレスから"
            f"{comments_count}件をピックアップしました。"
        )
        yield (
            status, thread_html_final, matome_html, raw_log,
            str(zip_path),
        )

    except RateLimitError as e:
        yield (
            f"レートリミットエラー: {e}\n\n"
            f"ウェイトタイムを増やすか、"
            f"しばらく待ってから再試行してください。",
            "", "", "", None,
        )
    except RuntimeError as e:
        yield (f"設定エラー: {e}", "", "", "", None)
    except ConnectionError:
        yield (
            "接続エラー: サーバーに接続できません。"
            "サーバーが起動しているか、URLが正しいか確認してください。",
            "", "", "", None,
        )
    except Exception as e:
        tb = traceback.format_exc()
        if "429" in str(e) or "RateLimit" in str(e):
            yield (
                f"レートリミットエラー: {e}\n\n"
                f"ウェイトタイムを増やすか、"
                f"しばらく待ってから再試行してください。",
                "", "", "", None,
            )
        else:
            yield (
                f"エラーが発生しました: {e}\n\n{tb}",
                "", "", "", None,
            )


def save_settings_from_ui(
    tones: list[str],
    conv_count: float,
    participant_count: float,
    auto_title_flag: bool,
    disc_provider: str,
    disc_model: str,
    sum_provider: str,
    sum_model: str,
    wait_time_sec: float,
    ollama_url: str,
    lmstudio_url: str,
    openrouter_url: str,
    custom_openai_url: str,
    custom_openai_api_key: str,
    disc_mapping: dict[str, str],
    sum_mapping: dict[str, str],
) -> str:
    """「設定を保存」ボタン押下時にUI設定をJSONに保存する"""
    _save_ui_settings({
        "tone": tones,
        "conv_count": int(conv_count),
        "participant_count": int(participant_count),
        "auto_title": auto_title_flag,
        "disc_provider": disc_provider,
        "disc_model": disc_model,
        "sum_provider": sum_provider,
        "sum_model": sum_model,
        "wait_time": wait_time_sec,
        "ollama_url": ollama_url,
        "lmstudio_url": lmstudio_url,
        "openrouter_url": openrouter_url,
        "custom_openai_url": custom_openai_url,
        "custom_openai_api_key": custom_openai_api_key,
        "disc_provider_models": disc_mapping,
        "sum_provider_models": sum_mapping,
    })
    return "設定を保存しました。次回起動時に自動で反映されます。"


def toggle_manual_title(auto_flag: bool) -> dict:
    """スレタイ自動生成チェックの状態に応じて手動入力欄を切り替える"""
    return gr.update(visible=not auto_flag)


# 起動時にUI設定を読み込む
_ui = _load_ui_settings()

# GradioのカスタムCSS
CUSTOM_CSS = """
.gradio-container {
    max-width: 1200px !important;
}
"""

# Gradio UIの構築
with gr.Blocks(
    title="2ch/5chまとめ風ジェネレーター",
) as app:
    # プロバイダー→モデル名マッピングを gr.State で管理
    disc_provider_models_state = gr.State(
        value=_ui.get(
            "disc_provider_models",
            dict(_DEFAULT_PROVIDER_MODELS),
        )
    )
    sum_provider_models_state = gr.State(
        value=_ui.get(
            "sum_provider_models",
            dict(_DEFAULT_SUM_PROVIDER_MODELS),
        )
    )

    gr.Markdown("# 2ch/5chまとめ風ジェネレーター")
    gr.Markdown(
        "テーマを入力すると、複数のAIエージェントが"
        "2ちゃんねらー風に議論を行い、"
        "まとめサイト風に自動編集します。"
        "「スレッド」タブで議論の進行をリアルタイムに見られます。"
    )

    # ===== トップレベルのタブ =====
    with gr.Tabs():

        # ===== メインタブ =====
        with gr.TabItem("メイン"):
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
                        value=_ui.get("tone", ["通常"]),
                        label="議論のトーン（複数選択可）",
                    )
                    conv_count = gr.Slider(
                        minimum=5, maximum=100,
                        value=_ui.get("conv_count", 20),
                        step=5,
                        label="会話数",
                        info=(
                            "会話数が多いほどAPIコストと生成時間が"
                            "増加します"
                        ),
                    )
                    participant_count = gr.Slider(
                        minimum=2, maximum=10,
                        value=_ui.get("participant_count", 5),
                        step=1,
                        label="参加人数",
                    )
                    image_input = gr.Image(
                        label="参考画像（任意）",
                        type="filepath",
                    )
                    file_input = gr.File(
                        label="参考ファイル（任意）",
                    )

                    with gr.Accordion(
                        "参考情報（URL・検索）", open=False
                    ):
                        ref_urls_input = gr.Textbox(
                            label="参考URL（任意・1行1URL）",
                            lines=3,
                            placeholder=(
                                "https://example.com/article1\n"
                                "https://example.com/article2\n"
                                "※テーマ欄のURLも自動検出します"
                            ),
                        )
                        search_keywords_input = gr.Textbox(
                            label="Web検索キーワード（任意）",
                            lines=1,
                            placeholder=(
                                "例: エヴァンゲリオン "
                                "新作 最新情報"
                            ),
                            info=(
                                "DuckDuckGoで検索し上位5件の情報を"
                                "議論の参考にします（APIキー不要）"
                            ),
                        )

                    auto_title = gr.Checkbox(
                        value=_ui.get("auto_title", True),
                        label="スレッドタイトルをAIが自動生成",
                    )
                    manual_title = gr.Textbox(
                        label="手動スレッドタイトル",
                        visible=not _ui.get("auto_title", True),
                        placeholder="スレッドタイトルを入力...",
                    )
                    auto_title.change(
                        fn=toggle_manual_title,
                        inputs=[auto_title],
                        outputs=[manual_title],
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
                            "「まとめを生成する」を押すと"
                            "処理が始まります"
                        ),
                    )

                    with gr.Tabs():
                        with gr.TabItem("スレッド"):
                            thread_output = gr.HTML(
                                label=(
                                    "スレッド表示"
                                    "（リアルタイム）"
                                ),
                            )
                        with gr.TabItem("まとめ表示"):
                            html_output = gr.HTML(
                                label="まとめ風表示",
                            )
                        with gr.TabItem("生ログ"):
                            raw_log = gr.Textbox(
                                label="議論の生ログ",
                                lines=20,
                                interactive=False,
                            )

                    gr.Markdown(
                        "### 一括ダウンロード\n"
                        "スレッド・まとめ・生ログの各データを "
                        "`.txt` / `.json` / `.html` の"
                        "9ファイルに書き出し、"
                        "ZIPにまとめてダウンロードできます。"
                    )
                    zip_download = gr.File(
                        label=(
                            "全データ一括ダウンロード（ZIP）"
                        ),
                    )

        # ===== 詳細設定タブ =====
        with gr.TabItem("詳細設定"):
            gr.Markdown(
                "## 詳細設定\n"
                "LLMプロバイダー・モデル・接続先などを"
                "設定します。\n"
                "プロバイダーを切り替えると、"
                "前回そのプロバイダーで使ったモデル名が"
                "自動で復元されます。\n"
                "「設定を保存」を押すと "
                "`config/ui_settings.json` に保存され、"
                "次回起動時に自動で反映されます。"
            )

            with gr.Row():
                with gr.Column():
                    gr.Markdown("### 議論用LLM")
                    disc_provider = gr.Dropdown(
                        choices=ALL_PROVIDERS,
                        value=_ui.get(
                            "disc_provider", "gemini"
                        ),
                        label="議論用LLMプロバイダー",
                        info=(
                            "openrouter: OpenRouter経由で"
                            "多数モデル利用可 / "
                            "custom_openai: 任意の"
                            "OpenAI互換API"
                        ),
                    )
                    disc_model = gr.Textbox(
                        value=_ui.get(
                            "disc_model",
                            "gemini-3.1-flash-lite-preview",
                        ),
                        label="議論用モデル名",
                        info=(
                            "OpenRouterの場合は"
                            "「openai/gpt-5-mini」のように"
                            "プロバイダー/モデル名の形式"
                        ),
                    )

                with gr.Column():
                    gr.Markdown("### まとめ用LLM")
                    sum_provider = gr.Dropdown(
                        choices=ALL_PROVIDERS,
                        value=_ui.get(
                            "sum_provider", "gemini"
                        ),
                        label="まとめ用LLMプロバイダー",
                    )
                    sum_model = gr.Textbox(
                        value=_ui.get(
                            "sum_model",
                            "gemini-3-flash-preview",
                        ),
                        label="まとめ用モデル名",
                    )

            # プロバイダー切替時のモデル名自動復元イベント
            disc_provider.change(
                fn=on_disc_provider_change,
                inputs=[
                    disc_provider,
                    disc_model,
                    disc_provider_models_state,
                ],
                outputs=[
                    disc_model,
                    disc_provider_models_state,
                ],
            )
            disc_model.change(
                fn=on_disc_model_change,
                inputs=[
                    disc_provider,
                    disc_model,
                    disc_provider_models_state,
                ],
                outputs=[disc_provider_models_state],
            )
            sum_provider.change(
                fn=on_sum_provider_change,
                inputs=[
                    sum_provider,
                    sum_model,
                    sum_provider_models_state,
                ],
                outputs=[
                    sum_model,
                    sum_provider_models_state,
                ],
            )
            sum_model.change(
                fn=on_sum_model_change,
                inputs=[
                    sum_provider,
                    sum_model,
                    sum_provider_models_state,
                ],
                outputs=[sum_provider_models_state],
            )

            gr.Markdown("### 共通設定")
            wait_time = gr.Slider(
                minimum=0.0, maximum=10.0,
                value=_ui.get("wait_time", 1.0),
                step=0.5,
                label="APIウェイトタイム（秒）",
                info=(
                    "リクエスト間の待機時間。"
                    "レートリミットエラーが出る場合は"
                    "増やしてください"
                ),
            )

            gr.Markdown("### ローカルサーバー設定")
            with gr.Row():
                ollama_url = gr.Textbox(
                    value=_ui.get(
                        "ollama_url",
                        "http://localhost:11434",
                    ),
                    label="Ollama サーバーURL",
                )
                lmstudio_url = gr.Textbox(
                    value=_ui.get(
                        "lmstudio_url",
                        "http://localhost:1234/v1",
                    ),
                    label="LM Studio サーバーURL",
                )

            gr.Markdown("### OpenRouter設定")
            gr.Markdown(
                "APIキーは `config/settings.yaml` の "
                "`api_keys.openrouter` に設定してください。"
                "[OpenRouter](https://openrouter.ai/) "
                "で取得できます。"
            )
            openrouter_url = gr.Textbox(
                value=_ui.get(
                    "openrouter_url",
                    "https://openrouter.ai/api/v1",
                ),
                label="OpenRouter ベースURL",
                info="通常は変更不要です",
            )

            gr.Markdown(
                "### カスタムOpenAI互換プロバイダー設定"
            )
            gr.Markdown(
                "Together AI, Groq, Fireworks, "
                "自社プロキシなど、"
                "OpenAI互換APIを提供するサービスに"
                "接続できます。"
            )
            with gr.Row():
                custom_openai_url = gr.Textbox(
                    value=_ui.get("custom_openai_url", ""),
                    label="カスタムOpenAI互換 ベースURL",
                    placeholder=(
                        "例: https://api.together.xyz/v1"
                    ),
                    info=(
                        "接続先のベースURL。"
                        "settings.yaml でも設定可能です"
                    ),
                )
                custom_openai_api_key = gr.Textbox(
                    value=_ui.get(
                        "custom_openai_api_key", ""
                    ),
                    label="カスタムOpenAI互換 APIキー",
                    placeholder="APIキー（不要なら空欄）",
                    type="password",
                    info=(
                        "ここに入力するとsettings.yamlの値より"
                        "優先されます。"
                        "APIキー不要のサービスは空欄のままでOK"
                    ),
                )

            # 設定保存ボタンとステータス
            with gr.Row():
                save_settings_btn = gr.Button(
                    "設定を保存",
                    variant="secondary",
                )
                settings_status = gr.Textbox(
                    label="",
                    interactive=False,
                    placeholder="",
                    show_label=False,
                )

            save_settings_btn.click(
                fn=save_settings_from_ui,
                inputs=[
                    tone_input, conv_count,
                    participant_count, auto_title,
                    disc_provider, disc_model,
                    sum_provider, sum_model,
                    wait_time, ollama_url,
                    lmstudio_url, openrouter_url,
                    custom_openai_url,
                    custom_openai_api_key,
                    disc_provider_models_state,
                    sum_provider_models_state,
                ],
                outputs=[settings_status],
            )

    # 生成ボタンのクリックイベント
    generate_btn.click(
        fn=generate_matome_streaming,
        inputs=[
            theme_input, context_input, tone_input, conv_count,
            participant_count, image_input, file_input,
            auto_title, manual_title, disc_provider, disc_model,
            sum_provider, sum_model, wait_time, ollama_url,
            lmstudio_url, openrouter_url, custom_openai_url,
            custom_openai_api_key, ref_urls_input,
            search_keywords_input,
            disc_provider_models_state,
            sum_provider_models_state,
        ],
        outputs=[
            status_text, thread_output, html_output, raw_log,
            zip_download,
        ],
    )

# エントリーポイント
if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", css=CUSTOM_CSS)
