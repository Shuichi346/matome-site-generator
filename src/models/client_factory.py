"""LLMクライアント生成ファクトリーモジュール

プロバイダー名とモデル名を受け取り、
対応するAutoGenのモデルクライアントを返す。
対応プロバイダー: openai / gemini / ollama / lmstudio / openrouter / custom_openai
"""

from pathlib import Path
from typing import Any

import yaml
from autogen_core.models import ModelInfo
from autogen_ext.models.openai import OpenAIChatCompletionClient


# Gemini OpenAI互換APIのベースURL
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# OpenRouterのデフォルトベースURL
OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# 全プロバイダー名のリスト（UI等で選択肢として使用）
ALL_PROVIDERS = [
    "openai",
    "gemini",
    "ollama",
    "lmstudio",
    "openrouter",
    "custom_openai",
]

# 設定ファイルのパス
SETTINGS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
)


def load_settings() -> dict[str, Any]:
    """設定ファイルを読み込む

    Returns:
        設定辞書。ファイルが存在しない場合は空辞書。
    """
    if not SETTINGS_PATH.exists():
        return {}
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _build_model_info(
    vision: bool = False,
    function_calling: bool = False,
    json_output: bool = True,
    structured_output: bool = False,
) -> ModelInfo:
    """ModelInfoを生成するヘルパー"""
    return ModelInfo(
        vision=vision,
        function_calling=function_calling,
        json_output=json_output,
        family="unknown",
        structured_output=structured_output,
    )


def create_model_client(
    provider: str,
    model_name: str,
    settings: dict[str, Any] | None = None,
    ollama_url: str = "http://localhost:11434",
    lmstudio_url: str = "http://localhost:1234/v1",
    openrouter_url: str = "",
    custom_openai_url: str = "",
    custom_openai_api_key: str = "",
) -> Any:
    """プロバイダーに応じたLLMクライアントを生成する

    Args:
        provider: プロバイダー名
        model_name: モデル名
        settings: 設定辞書（Noneの場合はファイルから読み込む）
        ollama_url: OllamaサーバーのURL
        lmstudio_url: LM StudioサーバーのURL
        openrouter_url: OpenRouterのベースURL（空ならsettingsまたはデフォルト）
        custom_openai_url: カスタムOpenAI互換のベースURL（空ならsettingsから取得）
        custom_openai_api_key: カスタムOpenAI互換のAPIキー（空ならsettingsから取得）

    Returns:
        AutoGenのChatCompletionClientインスタンス

    Raises:
        ValueError: 未対応のプロバイダーが指定された場合
        RuntimeError: APIキーやURLが設定されていない場合
    """
    if settings is None:
        settings = load_settings()

    api_keys = settings.get("api_keys", {})

    # --- OpenAI ---
    if provider == "openai":
        api_key = api_keys.get("openai", "")
        if not api_key or api_key.startswith("sk-your"):
            raise RuntimeError(
                "OpenAI APIキーが設定されていません。"
                "config/settings.yaml を編集してください。"
            )
        return OpenAIChatCompletionClient(
            model=model_name,
            api_key=api_key,
        )

    # --- Gemini ---
    if provider == "gemini":
        api_key = api_keys.get("gemini", "")
        if not api_key or api_key.startswith("your-"):
            raise RuntimeError(
                "Gemini APIキーが設定されていません。"
                "config/settings.yaml を編集してください。"
            )
        return OpenAIChatCompletionClient(
            model=model_name,
            api_key=api_key,
            base_url=GEMINI_BASE_URL,
            model_info=_build_model_info(
                vision=True,
                function_calling=True,
                json_output=True,
                structured_output=True,
            ),
        )

    # --- Ollama ---
    if provider == "ollama":
        try:
            from autogen_ext.models.ollama import OllamaChatCompletionClient
        except ImportError as e:
            raise RuntimeError(
                "Ollamaクライアントのインポートに失敗しました。"
                "autogen-ext[ollama] がインストールされているか確認してください。"
            ) from e
        return OllamaChatCompletionClient(
            model=model_name,
            host=ollama_url,
            model_info=_build_model_info(),
        )

    # --- LM Studio ---
    if provider == "lmstudio":
        return OpenAIChatCompletionClient(
            model=model_name,
            base_url=lmstudio_url,
            api_key="lm-studio",
            model_info=_build_model_info(),
        )

    # --- OpenRouter ---
    if provider == "openrouter":
        api_key = api_keys.get("openrouter", "")
        if not api_key or "your-key" in api_key:
            raise RuntimeError(
                "OpenRouter APIキーが設定されていません。"
                "config/settings.yaml の api_keys.openrouter を編集してください。"
            )
        # ベースURL: UI指定 → settings指定 → デフォルト の優先順
        base_url = openrouter_url.strip() if openrouter_url.strip() else ""
        if not base_url:
            or_settings = settings.get("openrouter", {})
            if isinstance(or_settings, dict):
                base_url = or_settings.get("base_url", "")
        if not base_url:
            base_url = OPENROUTER_DEFAULT_BASE_URL

        return OpenAIChatCompletionClient(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            model_info=_build_model_info(
                vision=True,
                function_calling=True,
                json_output=True,
                structured_output=True,
            ),
        )

    # --- カスタムOpenAI互換 ---
    if provider == "custom_openai":
        co_settings = settings.get("custom_openai", {})
        if not isinstance(co_settings, dict):
            co_settings = {}

        # ベースURL: UI指定 → settings指定
        base_url = custom_openai_url.strip() if custom_openai_url.strip() else ""
        if not base_url:
            base_url = co_settings.get("base_url", "")
        if not base_url:
            raise RuntimeError(
                "カスタムOpenAI互換のベースURLが設定されていません。"
                "UIの「カスタムOpenAI互換 ベースURL」欄、"
                "または config/settings.yaml の custom_openai.base_url を設定してください。"
            )

        # APIキー: UI指定 → settings指定 → "none"（不要なサービス用）
        api_key = custom_openai_api_key.strip() if custom_openai_api_key.strip() else ""
        if not api_key:
            api_key = co_settings.get("api_key", "")
        if not api_key:
            api_key = "none"

        # モデル能力: settingsから取得
        mi_conf = co_settings.get("model_info", {})
        if not isinstance(mi_conf, dict):
            mi_conf = {}

        return OpenAIChatCompletionClient(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            model_info=_build_model_info(
                vision=bool(mi_conf.get("vision", False)),
                function_calling=bool(mi_conf.get("function_calling", False)),
                json_output=bool(mi_conf.get("json_output", True)),
                structured_output=bool(mi_conf.get("structured_output", False)),
            ),
        )

    raise ValueError(
        f"未対応のプロバイダー: {provider}。"
        f"{', '.join(ALL_PROVIDERS)} のいずれかを指定してください。"
    )
