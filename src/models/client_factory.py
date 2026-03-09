"""LLMクライアント生成ファクトリーモジュール

プロバイダー名とモデル名を受け取り、
対応するAutoGenのモデルクライアントを返す。
対応プロバイダー: openai / gemini / ollama / openrouter / custom_openai
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
    "openrouter",
    "custom_openai",
]

# 設定ファイルのパス
SETTINGS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
)

_DEFAULT_MODEL_INFO_CONFIG: dict[str, bool] = {
    "vision": False,
    "function_calling": False,
    "json_output": True,
    "structured_output": False,
}

_VISION_PROVIDER_MODEL_INFO: dict[str, bool] = {
    "vision": True,
    "function_calling": True,
    "json_output": True,
    "structured_output": True,
}


def load_settings() -> dict[str, Any]:
    """設定ファイルを読み込む"""
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


def _coerce_model_info_config(
    config: Any,
    defaults: dict[str, bool],
) -> dict[str, bool]:
    """設定値からModelInfo用の辞書を組み立てる"""
    normalized = dict(defaults)
    if not isinstance(config, dict):
        return normalized

    for key in normalized:
        if key in config:
            normalized[key] = bool(config[key])
    return normalized


def get_model_info_for_provider(
    provider: str,
    settings: dict[str, Any] | None = None,
) -> ModelInfo:
    """プロバイダー別のModelInfoを返す"""
    if settings is None:
        settings = load_settings()

    if provider in {"openai", "gemini", "openrouter"}:
        config = dict(_VISION_PROVIDER_MODEL_INFO)
    elif provider == "ollama":
        ollama_settings = settings.get("ollama", {})
        if not isinstance(ollama_settings, dict):
            ollama_settings = {}
        config = _coerce_model_info_config(
            ollama_settings.get("model_info"),
            _DEFAULT_MODEL_INFO_CONFIG,
        )
    elif provider == "custom_openai":
        custom_settings = settings.get("custom_openai", {})
        if not isinstance(custom_settings, dict):
            custom_settings = {}
        config = _coerce_model_info_config(
            custom_settings.get("model_info"),
            _DEFAULT_MODEL_INFO_CONFIG,
        )
    else:
        raise ValueError(
            f"未対応のプロバイダー: {provider}。"
            f"{', '.join(ALL_PROVIDERS)} のいずれかを指定してください。"
        )

    return _build_model_info(
        vision=config["vision"],
        function_calling=config["function_calling"],
        json_output=config["json_output"],
        structured_output=config["structured_output"],
    )


def provider_supports_vision(
    provider: str,
    settings: dict[str, Any] | None = None,
) -> bool:
    """プロバイダー設定上でvision対応かどうかを返す"""
    return bool(get_model_info_for_provider(provider, settings)["vision"])


def create_model_client(
    provider: str,
    model_name: str,
    settings: dict[str, Any] | None = None,
    ollama_url: str = "http://localhost:11434",
    openrouter_url: str = "",
    custom_openai_url: str = "",
    custom_openai_api_key: str = "",
    ollama_think: bool | None = None,
) -> Any:
    """プロバイダーに応じたLLMクライアントを生成する"""
    if settings is None:
        settings = load_settings()

    api_keys = settings.get("api_keys", {})
    model_info = get_model_info_for_provider(provider, settings)

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
            model_info=model_info,
        )

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
            model_info=model_info,
        )

    if provider == "ollama":
        try:
            from autogen_ext.models.ollama import OllamaChatCompletionClient
        except ImportError as e:
            raise RuntimeError(
                "Ollamaクライアントのインポートに失敗しました。"
                "autogen-ext[ollama] がインストールされているか確認してください。"
            ) from e

        kwargs: dict[str, Any] = {
            "model": model_name,
            "host": ollama_url,
            "model_info": model_info,
        }
        if ollama_think is not None:
            kwargs["think"] = ollama_think
        return OllamaChatCompletionClient(**kwargs)

    if provider == "openrouter":
        api_key = api_keys.get("openrouter", "")
        if not api_key or "your-key" in api_key:
            raise RuntimeError(
                "OpenRouter APIキーが設定されていません。"
                "config/settings.yaml の api_keys.openrouter を編集してください。"
            )

        base_url = openrouter_url.strip() if openrouter_url.strip() else ""
        if not base_url:
            openrouter_settings = settings.get("openrouter", {})
            if isinstance(openrouter_settings, dict):
                base_url = openrouter_settings.get("base_url", "")
        if not base_url:
            base_url = OPENROUTER_DEFAULT_BASE_URL

        return OpenAIChatCompletionClient(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            model_info=model_info,
        )

    if provider == "custom_openai":
        custom_settings = settings.get("custom_openai", {})
        if not isinstance(custom_settings, dict):
            custom_settings = {}

        base_url = custom_openai_url.strip() if custom_openai_url.strip() else ""
        if not base_url:
            base_url = custom_settings.get("base_url", "")
        if not base_url:
            raise RuntimeError(
                "カスタムOpenAI互換のベースURLが設定されていません。"
                "UIの「カスタムOpenAI互換 ベースURL」欄、"
                "または config/settings.yaml の custom_openai.base_url を設定してください。"
            )

        api_key = (
            custom_openai_api_key.strip()
            if custom_openai_api_key.strip()
            else ""
        )
        if not api_key:
            api_key = custom_settings.get("api_key", "")
        if not api_key:
            api_key = "none"

        return OpenAIChatCompletionClient(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            model_info=model_info,
        )

    raise ValueError(
        f"未対応のプロバイダー: {provider}。"
        f"{', '.join(ALL_PROVIDERS)} のいずれかを指定してください。"
    )
