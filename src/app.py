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
スレッドタイトルは常にAIが自動生成する。
議論の途中停止はExternalTerminationで穏当に行う。
進捗時間見積もり・テーマプリセットに対応。
Ollamaのthinking設定は議論用・まとめ用で個別に指定可能。
"""

import asyncio
import json
import re
import time
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import gradio as gr

from src.agents.discussion import (
    RateLimitError,
    build_discussion_agents,
    close_discussion_agents,
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
from autogen_agentchat.conditions import ExternalTermination
from autogen_agentchat.messages import TextMessage

# 出力ディレクトリ
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# UI設定ファイルのパス
UI_SETTINGS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "ui_settings.json"
)

# プリセットファイルのパス
PRESETS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "presets.json"
)

# URLを検出する正規表現
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"'`\])},;]+"
)

# プロバイダーごとのデフォルトモデル名
_DEFAULT_PROVIDER_MODELS: dict[str, str] = {
    "openai": "gpt-5-mini",
    "gemini": "gemini-3.1-flash-lite-preview",
    "ollama": "model-name",
    "openrouter": "stepfun/step-3.5-flash:free",
    "custom_openai": "model-name",
}

# まとめ用のデフォルト
_DEFAULT_SUM_PROVIDER_MODELS: dict[str, str] = {
    "openai": "gpt-5.4",
    "gemini": "gemini-3-flash-preview",
    "ollama": "model-name",
    "openrouter": "stepfun/step-3.5-flash:free",
    "custom_openai": "model-name",
}

# Ollama thinking設定の選択肢
_OLLAMA_THINK_CHOICES = ["モデルのデフォルト", "ON", "OFF"]

# UI設定のデフォルト値
_DEFAULT_UI_SETTINGS: dict[str, Any] = {
    "tone": ["通常"],
    "conv_count": 20,
    "participant_count": 5,
    "disc_provider": "gemini",
    "disc_model": "gemini-3.1-flash-lite-preview",
    "sum_provider": "gemini",
    "sum_model": "gemini-3-flash-preview",
    "wait_time": 1.0,
    "ollama_url": "http://localhost:11434",
    "openrouter_url": "https://openrouter.ai/api/v1",
    "custom_openai_url": "",
    "custom_openai_api_key": "",
    "disc_provider_models": dict(_DEFAULT_PROVIDER_MODELS),
    "sum_provider_models": dict(_DEFAULT_SUM_PROVIDER_MODELS),
    "max_search_results": 3,
    "max_url_content_length": 2000,
    "search_content_mode": "snippet",
    "max_context_messages": 10,
    "ollama_disc_think": "OFF",
    "ollama_sum_think": "OFF",
}

# プリセット選択肢の「選択なし」項目
_PRESET_NONE = "（選択なし）"


def _parse_ollama_think(value: str) -> bool | None:
    """UIのthinking選択肢をbool | Noneに変換する"""
    if value == "ON":
        return True
    if value == "OFF":
        return False
    return None


# ========================================
# 停止管理（ExternalTermination方式）
# ========================================
_current_stop_termination: ExternalTermination | None = None
_stop_requested = False


def _request_cancel() -> str:
    """中止ボタン押下時に議論を穏当に停止する"""
    global _current_stop_termination, _stop_requested

    if _current_stop_termination is None:
        return "停止できる処理はありません。"

    _current_stop_termination.set()
    _stop_requested = True
    return "中止を要求しました。現在のレス生成が終わり次第停止します..."


# ========================================
# プリセット管理
# ========================================

def _load_presets() -> dict[str, dict[str, str]]:
    """プリセットをJSONファイルから読み込む"""
    if not PRESETS_PATH.exists():
        return {}

    try:
        with open(PRESETS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    presets = data.get("presets")
    if not isinstance(presets, dict):
        return {}

    return presets


def _save_presets(presets: dict[str, dict[str, str]]) -> None:
    """プリセットをJSONファイルに保存する"""
    PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"presets": presets},
            f, ensure_ascii=False, indent=2,
        )


def _get_preset_choices() -> list[str]:
    """プリセットのドロップダウン選択肢リストを返す"""
    presets = _load_presets()
    return [_PRESET_NONE] + sorted(presets.keys())


def on_preset_select(
    preset_name: str,
) -> tuple[str, str]:
    """プリセットが選択された時にテーマと方向性を返す"""
    if preset_name == _PRESET_NONE or not preset_name:
        return "", ""
    presets = _load_presets()
    preset = presets.get(preset_name, {})
    return preset.get("theme", ""), preset.get("context", "")


def save_preset(
    preset_name: str,
    theme: str,
    context: str,
) -> tuple[Any, str]:
    """現在のテーマ・方向性をプリセットとして保存する"""
    if not preset_name.strip():
        return gr.skip(), "エラー: プリセット名を入力してください。"
    presets = _load_presets()
    presets[preset_name.strip()] = {
        "theme": theme,
        "context": context,
    }
    _save_presets(presets)
    new_choices = _get_preset_choices()
    return (
        gr.Dropdown(choices=new_choices, value=preset_name.strip()),
        f"プリセット「{preset_name.strip()}」を保存しました。",
    )


def delete_preset(
    preset_name: str,
) -> tuple[Any, str]:
    """選択中のプリセットを削除する"""
    if preset_name == _PRESET_NONE or not preset_name:
        return gr.skip(), "削除するプリセットが選択されていません。"
    presets = _load_presets()
    if preset_name in presets:
        del presets[preset_name]
        _save_presets(presets)
        new_choices = _get_preset_choices()
        return (
            gr.Dropdown(choices=new_choices, value=_PRESET_NONE),
            f"プリセット「{preset_name}」を削除しました。",
        )
    return gr.skip(), f"プリセット「{preset_name}」が見つかりません。"


# ========================================
# UI設定の読み書き
# ========================================

def _load_ui_settings() -> dict[str, Any]:
    """UI設定をJSONファイルから読み込む

    優先順位:
      1. ui_settings.json に値がある → その値を使う
      2. ui_settings.json がない → settings.yaml の値を使う
      3. settings.yaml にもない → _DEFAULT_UI_SETTINGS の値を使う
    """
    settings = json.loads(json.dumps(_DEFAULT_UI_SETTINGS))

    # settings.yaml からフォールバック値を取得する
    yaml_settings = load_settings()

    # defaults セクション
    defaults = yaml_settings.get("defaults", {})
    if isinstance(defaults, dict):
        if "discussion_provider" in defaults:
            settings["disc_provider"] = defaults["discussion_provider"]
        if "discussion_model" in defaults:
            settings["disc_model"] = defaults["discussion_model"]
        if "summarizer_provider" in defaults:
            settings["sum_provider"] = defaults["summarizer_provider"]
        if "summarizer_model" in defaults:
            settings["sum_model"] = defaults["summarizer_model"]
        if "wait_time_seconds" in defaults:
            settings["wait_time"] = float(defaults["wait_time_seconds"])

    # local_servers セクション
    local_servers = yaml_settings.get("local_servers", {})
    if isinstance(local_servers, dict):
        if "ollama_base_url" in local_servers:
            settings["ollama_url"] = local_servers["ollama_base_url"]

    # openrouter セクション
    openrouter = yaml_settings.get("openrouter", {})
    if isinstance(openrouter, dict):
        if "base_url" in openrouter:
            settings["openrouter_url"] = openrouter["base_url"]

    # custom_openai セクション
    custom_openai = yaml_settings.get("custom_openai", {})
    if isinstance(custom_openai, dict):
        if "base_url" in custom_openai and custom_openai["base_url"]:
            settings["custom_openai_url"] = custom_openai["base_url"]
        if "api_key" in custom_openai and custom_openai["api_key"]:
            settings["custom_openai_api_key"] = custom_openai["api_key"]

    # web_fetch セクション
    web_fetch = yaml_settings.get("web_fetch", {})
    if isinstance(web_fetch, dict):
        if "max_search_results" in web_fetch:
            settings["max_search_results"] = int(
                web_fetch["max_search_results"]
            )
        if "max_url_content_length" in web_fetch:
            settings["max_url_content_length"] = int(
                web_fetch["max_url_content_length"]
            )
        if "search_content_mode" in web_fetch:
            settings["search_content_mode"] = (
                web_fetch["search_content_mode"]
            )

    # ollama thinking セクション
    ollama_conf = yaml_settings.get("ollama", {})
    if isinstance(ollama_conf, dict):
        yaml_disc_think = ollama_conf.get("discussion_think")
        yaml_sum_think = ollama_conf.get("summarizer_think")
        if yaml_disc_think is True:
            settings["ollama_disc_think"] = "ON"
        elif yaml_disc_think is False:
            settings["ollama_disc_think"] = "OFF"
        if yaml_sum_think is True:
            settings["ollama_sum_think"] = "ON"
        elif yaml_sum_think is False:
            settings["ollama_sum_think"] = "OFF"

    # プロバイダーモデルマッピングも defaults に合わせて更新する
    if "disc_provider" in settings and "disc_model" in settings:
        settings["disc_provider_models"][settings["disc_provider"]] = (
            settings["disc_model"]
        )
    if "sum_provider" in settings and "sum_model" in settings:
        settings["sum_provider_models"][settings["sum_provider"]] = (
            settings["sum_model"]
        )

    # ui_settings.json があれば上書きする（最優先）
    if UI_SETTINGS_PATH.exists():
        try:
            with open(UI_SETTINGS_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                saved.pop("auto_title", None)
                # LM Studio関連の古い設定を無視する
                saved.pop("lmstudio_url", None)
                for key in ("disc_provider_models", "sum_provider_models"):
                    if key in saved and isinstance(saved[key], dict):
                        saved[key].pop("lmstudio", None)
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


def _build_ui_settings_payload(
    tones: list[str],
    conv_count: float,
    participant_count: float,
    disc_provider: str,
    disc_model: str,
    sum_provider: str,
    sum_model: str,
    wait_time_sec: float,
    ollama_url: str,
    openrouter_url: str,
    custom_openai_url: str,
    custom_openai_api_key: str,
    disc_mapping: dict[str, str],
    sum_mapping: dict[str, str],
    max_search_results: int,
    max_url_content_length: int,
    search_content_mode: str,
    max_context_messages: int,
    ollama_disc_think: str,
    ollama_sum_think: str,
) -> dict[str, Any]:
    """UI設定保存用の辞書を組み立てる"""
    return {
        "tone": list(tones or []),
        "conv_count": int(conv_count),
        "participant_count": int(participant_count),
        "disc_provider": disc_provider,
        "disc_model": disc_model,
        "sum_provider": sum_provider,
        "sum_model": sum_model,
        "wait_time": wait_time_sec,
        "ollama_url": ollama_url,
        "openrouter_url": openrouter_url,
        "custom_openai_url": custom_openai_url,
        "custom_openai_api_key": custom_openai_api_key,
        "disc_provider_models": dict(disc_mapping or {}),
        "sum_provider_models": dict(sum_mapping or {}),
        "max_search_results": int(max_search_results),
        "max_url_content_length": int(max_url_content_length),
        "search_content_mode": search_content_mode,
        "max_context_messages": int(max_context_messages),
        "ollama_disc_think": ollama_disc_think,
        "ollama_sum_think": ollama_sum_think,
    }


# ========================================
# ユーティリティ
# ========================================

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


def _render_cancelled_notice(res_number: int, conv_count: int) -> str:
    """キャンセル時のHTML通知を生成する"""
    notice_style = (
        "margin:12px 8px;padding:14px 20px;"
        "background:#d1ecf1;border:2px solid #bee5eb;"
        "border-radius:8px;font-size:0.92em;"
        "color:#0c5460;line-height:1.6;"
    )
    return f"""
    <div style="{notice_style}">
      &#9209; 生成を中止しました（{res_number}/{conv_count}レス）。
      途中までのレスでまとめを生成しています...
    </div>"""


def _format_time_estimate(seconds: float) -> str:
    """秒数を「約○分○秒」の文字列に変換する"""
    if seconds < 0:
        return "計算中..."
    if seconds < 60:
        return f"約{int(seconds)}秒"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if secs == 0:
        return f"約{minutes}分"
    return f"約{minutes}分{secs}秒"


# ========================================
# プロバイダー切替時のモデル名自動復元
# ========================================

def on_disc_provider_change(
    new_provider: str,
    mapping: dict[str, str],
) -> tuple[str, dict[str, str]]:
    """議論用プロバイダーが変更された時にモデル名を復元する"""
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
    """議論用モデル名が手動変更された時にマッピングを更新する"""
    if new_model.strip():
        mapping[provider] = new_model.strip()
    return mapping


def on_sum_provider_change(
    new_provider: str,
    mapping: dict[str, str],
) -> tuple[str, dict[str, str]]:
    """まとめ用プロバイダーが変更された時にモデル名を復元する"""
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
    """まとめ用モデル名が手動変更された時にマッピングを更新する"""
    if new_model.strip():
        mapping[provider] = new_model.strip()
    return mapping


# ========================================
# 出力ファイル生成ヘルパー
# ========================================

def _generate_export_files(
    matome_data: dict[str, Any],
    thread_posts_data: list[dict[str, Any]],
    thread_title: str,
    res_number: int,
    raw_log_lines: list[str],
    raw_log_entries: list[dict[str, str]],
    timestamp: str,
) -> Path:
    """9ファイル＋ZIPを生成し、ZIPパスを返す"""
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
    return zip_path


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
    disc_provider: str,
    disc_model: str,
    sum_provider: str,
    sum_model: str,
    wait_time_sec: float,
    ollama_url: str,
    openrouter_url: str,
    custom_openai_url: str,
    custom_openai_api_key: str,
    ref_urls: str,
    search_keywords: str,
    max_search_results: float,
    max_url_content_length: float,
    search_content_mode: str,
    max_context_messages: float,
    disc_mapping: dict[str, str],
    sum_mapping: dict[str, str],
    ollama_disc_think: str,
    ollama_sum_think: str,
):
    """まとめ生成の全パイプライン（非同期ジェネレーター）

    Yields:
        (ステータス, スレッドHTML, まとめHTML, 生ログ, ZIPパス)
    """
    global _current_stop_termination
    global _stop_requested

    conv_count = int(conv_count)
    participant_count = int(participant_count)

    if not theme.strip():
        yield ("エラー: テーマを入力してください。", "", "", "", None)
        return

    # thinking設定をパースする
    disc_think = _parse_ollama_think(ollama_disc_think)
    sum_think = _parse_ollama_think(ollama_sum_think)

    # 生成開始時にUI設定を保存する
    _save_ui_settings(
        _build_ui_settings_payload(
            tones=tones,
            conv_count=conv_count,
            participant_count=participant_count,
            disc_provider=disc_provider,
            disc_model=disc_model,
            sum_provider=sum_provider,
            sum_model=sum_model,
            wait_time_sec=wait_time_sec,
            ollama_url=ollama_url,
            openrouter_url=openrouter_url,
            custom_openai_url=custom_openai_url,
            custom_openai_api_key=custom_openai_api_key,
            disc_mapping=disc_mapping,
            sum_mapping=sum_mapping,
            max_search_results=int(max_search_results),
            max_url_content_length=int(max_url_content_length),
            search_content_mode=search_content_mode,
            max_context_messages=int(max_context_messages),
            ollama_disc_think=ollama_disc_think,
            ollama_sum_think=ollama_sum_think,
        )
    )

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
        url_results = await fetch_multiple_urls(
            unique_urls,
            max_length=int(max_url_content_length),
        )
        url_context = format_url_results_as_context(
            url_results,
            snippet_only=(search_content_mode == "snippet"),
        )
        extra_context += url_context

    # Web検索
    if search_keywords.strip():
        yield (
            f"「{search_keywords.strip()}」でWeb検索中...",
            "", "", "", None,
        )
        search_results = await search_web(
            search_keywords.strip(),
            max_results=int(max_search_results),
            max_length=int(max_url_content_length),
            fetch_body=(search_content_mode == "full"),
        )
        search_context = format_search_results_as_context(
            search_results
        )
        extra_context += search_context

    full_context = context + extra_context
    display_text = _build_display_text(theme, context)

    provider_kwargs = {
        "ollama_url": ollama_url,
        "openrouter_url": openrouter_url,
        "custom_openai_url": custom_openai_url,
        "custom_openai_api_key": custom_openai_api_key,
    }

    agents = []

    try:
        # ステップ1: ペルソナ生成
        yield ("ペルソナを生成中...", "", "", "", None)
        personas = generate_personas(participant_count, tones)
        agent_map = _build_agent_persona_map(personas)

        # ステップ2: スレタイ生成
        yield ("スレッドタイトルを生成中...", "", "", "", None)
        thread_title = await generate_thread_title(
            theme=theme,
            provider=sum_provider,
            model_name=sum_model,
            rate_limiter=rate_limiter,
            settings=settings,
            ollama_think=sum_think,
            **provider_kwargs,
        )

        # ステップ3: 議論用エージェント構築
        yield ("議論用エージェントを構築中...", "", "", "", None)
        agents = build_discussion_agents(
            personas=personas,
            theme=theme,
            context=context,
            tones=tones,
            provider=disc_provider,
            model_name=disc_model,
            rate_limiter=rate_limiter,
            settings=settings,
            max_context_messages=int(max_context_messages),
            ollama_think=disc_think,
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
        rate_limit_msg = ""
        was_cancelled = False

        # 時間見積もり用
        res_timestamps: list[float] = []

        # ExternalTerminationを生成しグローバルに保持する
        stop_termination = ExternalTermination()
        _current_stop_termination = stop_termination
        _stop_requested = False

        try:
            stream = run_discussion_stream(
                agents=agents,
                thread_title=thread_title,
                theme=(
                    f"{theme}\n\n{full_context}"
                    if full_context else theme
                ),
                conversation_count=conv_count,
                external_termination=stop_termination,
            )

            async for item in stream:
                if isinstance(item, TaskResult):
                    discussion_result = item
                    continue

                if isinstance(item, TextMessage):
                    now_ts = time.monotonic()
                    res_number += 1
                    res_timestamps.append(now_ts)
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

                    # 時間見積もりを計算する
                    time_estimate_str = ""
                    remaining_count = conv_count - res_number
                    if (
                        len(res_timestamps) >= 2
                        and remaining_count > 0
                    ):
                        intervals = [
                            res_timestamps[j] - res_timestamps[j - 1]
                            for j in range(1, len(res_timestamps))
                        ]
                        avg_interval = (
                            sum(intervals) / len(intervals)
                        )
                        est_remaining = (
                            avg_interval * remaining_count
                        )
                        time_estimate_str = (
                            f" ─ 残り"
                            f"{_format_time_estimate(est_remaining)}"
                        )

                    status = (
                        f"議論を実行中... "
                        f"({res_number}/{conv_count}レス)"
                        f"{time_estimate_str}"
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

        except asyncio.CancelledError:
            was_cancelled = True

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

        finally:
            if _stop_requested:
                was_cancelled = True
            _current_stop_termination = None

            await close_discussion_agents(agents)

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

        if was_cancelled:
            thread_html_parts += _render_cancelled_notice(
                res_number, conv_count
            )

        thread_html_final = (
            thread_html_parts + render_thread_footer(res_number)
        )

        if res_number == 0:
            yield (
                "エラー: 議論のレスが1件も生成されませんでした。",
                thread_html_final, "", raw_log, None,
            )
            return

        # ステップ5: まとめ生成
        cancel_note = ""
        if was_cancelled:
            cancel_note = f"（中止: {res_number}/{conv_count}レス）"
        yield (
            f"まとめ記事を生成中...{cancel_note}",
            thread_html_final, "", raw_log, None,
        )

        try:
            if discussion_result is None:
                discussion_result = TaskResult(
                    messages=[
                        TextMessage(
                            content=entry["content"],
                            source=entry["source"],
                        )
                        for entry in raw_log_entries
                    ],
                    stop_reason=(
                        "cancelled" if was_cancelled else "unknown"
                    ),
                )

            matome_data = await run_summarizer(
                discussion_result=discussion_result,
                personas=personas,
                provider=sum_provider,
                model_name=sum_model,
                rate_limiter=rate_limiter,
                settings=settings,
                ollama_think=sum_think,
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

        zip_path = _generate_export_files(
            matome_data=matome_data,
            thread_posts_data=thread_posts_data,
            thread_title=thread_title,
            res_number=res_number,
            raw_log_lines=raw_log_lines,
            raw_log_entries=raw_log_entries,
            timestamp=timestamp,
        )

        comments_count = len(
            matome_data.get("thread_comments", [])
        )
        cancelled_note = ""
        if was_cancelled or res_number < conv_count:
            cancelled_note = (
                f"（{conv_count}レス中{res_number}レスで"
                f"{'中止' if was_cancelled else '中断'}） "
            )
        status = (
            f"完了！ {cancelled_note}"
            f"{res_number}件のレスから"
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
    disc_provider: str,
    disc_model: str,
    sum_provider: str,
    sum_model: str,
    wait_time_sec: float,
    ollama_url: str,
    openrouter_url: str,
    custom_openai_url: str,
    custom_openai_api_key: str,
    disc_mapping: dict[str, str],
    sum_mapping: dict[str, str],
    max_search_results: float,
    max_url_content_length: float,
    search_content_mode: str,
    max_context_messages: float,
    ollama_disc_think: str,
    ollama_sum_think: str,
) -> str:
    """「設定を保存」ボタン押下時にUI設定をJSONに保存する"""
    _save_ui_settings(
        _build_ui_settings_payload(
            tones=tones,
            conv_count=conv_count,
            participant_count=participant_count,
            disc_provider=disc_provider,
            disc_model=disc_model,
            sum_provider=sum_provider,
            sum_model=sum_model,
            wait_time_sec=wait_time_sec,
            ollama_url=ollama_url,
            openrouter_url=openrouter_url,
            custom_openai_url=custom_openai_url,
            custom_openai_api_key=custom_openai_api_key,
            disc_mapping=disc_mapping,
            sum_mapping=sum_mapping,
            max_search_results=int(max_search_results),
            max_url_content_length=int(max_url_content_length),
            search_content_mode=search_content_mode,
            max_context_messages=int(max_context_messages),
            ollama_disc_think=ollama_disc_think,
            ollama_sum_think=ollama_sum_think,
        )
    )
    return "設定を保存しました。次回起動時に自動で反映されます。"


# 起動時にUI設定を読み込む
_ui = _load_ui_settings()

# GradioのカスタムCSS（Gradio 6ではlaunch()に渡す）
CUSTOM_CSS = """
.gradio-container {
    max-width: 1200px !important;
}
#stop-btn {
    background: #dc3545 !important;
    color: white !important;
    border-color: #dc3545 !important;
}
#stop-btn:hover {
    background: #c82333 !important;
    border-color: #bd2130 !important;
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

                    # --- プリセット/テンプレート ---
                    with gr.Accordion(
                        "テーマのプリセット", open=False
                    ):
                        gr.Markdown(
                            "テンプレートを選ぶと、テーマ欄と方向性欄に"
                            "サンプルテキストが入ります。\n"
                            "プリセットを保存・削除することもできます。"
                        )
                        preset_dropdown = gr.Dropdown(
                            choices=_get_preset_choices(),
                            value=_PRESET_NONE,
                            label="プリセットを選択",
                            interactive=True,
                        )
                        with gr.Row():
                            preset_save_name = gr.Textbox(
                                label="保存名",
                                placeholder="プリセット名",
                                scale=3,
                            )
                            preset_save_btn = gr.Button(
                                "保存", scale=1, size="sm",
                            )
                            preset_delete_btn = gr.Button(
                                "削除", scale=1, size="sm",
                                variant="stop",
                            )
                        preset_status = gr.Textbox(
                            label="",
                            interactive=False,
                            show_label=False,
                            max_lines=1,
                        )

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

                    # プリセットイベント
                    preset_dropdown.change(
                        fn=on_preset_select,
                        inputs=[preset_dropdown],
                        outputs=[theme_input, context_input],
                    )
                    preset_save_btn.click(
                        fn=save_preset,
                        inputs=[
                            preset_save_name,
                            theme_input,
                            context_input,
                        ],
                        outputs=[preset_dropdown, preset_status],
                    )
                    preset_delete_btn.click(
                        fn=delete_preset,
                        inputs=[preset_dropdown],
                        outputs=[preset_dropdown, preset_status],
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

                    with gr.Row():
                        generate_btn = gr.Button(
                            "まとめを生成する",
                            variant="primary",
                            size="lg",
                            scale=3,
                        )
                        stop_btn = gr.Button(
                            "生成を中止",
                            variant="stop",
                            size="lg",
                            scale=1,
                            elem_id="stop-btn",
                            interactive=True,
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

            # プロバイダー切替イベント
            disc_provider.change(
                fn=on_disc_provider_change,
                inputs=[
                    disc_provider,
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

            gr.Markdown("### Ollama Thinking設定")
            gr.Markdown(
                "Ollamaの推論（thinking）モードを制御します。"
                "Qwen3、DeepSeek-R1 などの"
                "thinkingモデルで有効です。\n"
                "議論用とまとめ用で個別に設定できます。\n"
                "- **ON**: thinkingを有効化"
                "（精度向上・応答遅め）\n"
                "- **OFF**: thinkingを無効化"
                "（高速応答）\n"
                "- **モデルのデフォルト**: "
                "モデル側の既定動作に従う"
            )
            with gr.Row():
                ollama_disc_think = gr.Radio(
                    choices=_OLLAMA_THINK_CHOICES,
                    value=_ui.get(
                        "ollama_disc_think", "OFF"
                    ),
                    label="議論用 Thinking",
                    info=(
                        "Ollamaプロバイダー使用時のみ有効"
                    ),
                )
                ollama_sum_think = gr.Radio(
                    choices=_OLLAMA_THINK_CHOICES,
                    value=_ui.get(
                        "ollama_sum_think", "OFF"
                    ),
                    label="まとめ用 Thinking",
                    info=(
                        "Ollamaプロバイダー使用時のみ有効"
                    ),
                )

            gr.Markdown("### Web検索・URL取得設定")

            max_search_results = gr.Slider(
                minimum=1,
                maximum=10,
                value=_ui.get("max_search_results", 3),
                step=1,
                label="Web検索の取得件数",
                info=(
                    "DuckDuckGoで検索する上位サイトの数。"
                    "少ないほどトークン節約"
                ),
            )

            max_url_content_length = gr.Slider(
                minimum=500,
                maximum=10000,
                value=_ui.get("max_url_content_length", 2000),
                step=500,
                label="URL本文の最大文字数",
                info=(
                    "各URLから取得する本文の最大文字数。"
                    "少ないほどトークン節約"
                ),
            )

            search_content_mode = gr.Radio(
                choices=["snippet", "full"],
                value=_ui.get(
                    "search_content_mode", "snippet"
                ),
                label="検索結果の取得モード",
                info=(
                    "snippet=タイトルとスニペットのみ"
                    "（トークン大幅節約） / "
                    "full=各サイトの本文も取得"
                ),
            )

            gr.Markdown("### 会話履歴設定")

            max_context_messages = gr.Slider(
                minimum=0,
                maximum=50,
                value=_ui.get("max_context_messages", 10),
                step=1,
                label="エージェントに渡す会話履歴の最大件数",
                info=(
                    "各エージェントがレス生成時に参照する"
                    "直近の会話数。0=制限なし。"
                    "10程度推奨。"
                    "少ないほどトークン節約だが"
                    "文脈を失いやすい"
                ),
            )

            gr.Markdown("### ローカルサーバー設定")
            ollama_url = gr.Textbox(
                value=_ui.get(
                    "ollama_url",
                    "http://localhost:11434",
                ),
                label="Ollama サーバーURL",
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
                    participant_count,
                    disc_provider, disc_model,
                    sum_provider, sum_model,
                    wait_time, ollama_url,
                    openrouter_url,
                    custom_openai_url,
                    custom_openai_api_key,
                    disc_provider_models_state,
                    sum_provider_models_state,
                    max_search_results,
                    max_url_content_length,
                    search_content_mode,
                    max_context_messages,
                    ollama_disc_think,
                    ollama_sum_think,
                ],
                outputs=[settings_status],
            )

    # 生成ボタンのクリックイベント
    generate_btn.click(
        fn=generate_matome_streaming,
        inputs=[
            theme_input, context_input, tone_input, conv_count,
            participant_count, image_input, file_input,
            disc_provider, disc_model,
            sum_provider, sum_model, wait_time, ollama_url,
            openrouter_url, custom_openai_url,
            custom_openai_api_key, ref_urls_input,
            search_keywords_input,
            max_search_results,
            max_url_content_length,
            search_content_mode,
            max_context_messages,
            disc_provider_models_state,
            sum_provider_models_state,
            ollama_disc_think,
            ollama_sum_think,
        ],
        outputs=[
            status_text, thread_output, html_output, raw_log,
            zip_download,
        ],
    )

    # 中止ボタン
    stop_btn.click(
        fn=_request_cancel,
        inputs=None,
        outputs=[status_text],
    )

def main() -> None:
    """アプリケーションを起動する"""
    app.launch(server_name="127.0.0.1", css=CUSTOM_CSS)


# エントリーポイント
if __name__ == "__main__":
    main()
