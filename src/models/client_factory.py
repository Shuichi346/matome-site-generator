"""LLMクライアント生成ファクトリーモジュール

プロバイダー名とモデル名を受け取り、
対応するAutoGenのモデルクライアントを返す。
"""

from pathlib import Path
from typing import Any

import yaml
from autogen_core.models import ModelInfo
from autogen_ext.models.openai import OpenAIChatCompletionClient


# Gemini OpenAI互換APIのベースURL
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# 設定ファイルのパス
SETTINGS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"


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


def create_model_client(
    provider: str,
    model_name: str,
    settings: dict[str, Any] | None = None,
    ollama_url: str = "http://localhost:11434",
    lmstudio_url: str = "http://localhost:1234/v1",
) -> Any:
    """プロバイダーに応じたLLMクライアントを生成する

    Args:
        provider: プロバイダー名（openai / gemini / ollama / lmstudio）
        model_name: モデル名
        settings: 設定辞書（Noneの場合はファイルから読み込む）
        ollama_url: OllamaサーバーのURL
        lmstudio_url: LM StudioサーバーのURL

    Returns:
        AutoGenのChatCompletionClientインスタンス

    Raises:
        ValueError: 未対応のプロバイダーが指定された場合
        RuntimeError: APIキーが設定されていない場合
    """
    if settings is None:
        settings = load_settings()

    api_keys = settings.get("api_keys", {})

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
            model_info=ModelInfo(
                vision=True,
                function_calling=True,
                json_output=True,
                family="unknown",
                structured_output=True,
            ),
        )

    if provider == "ollama":
        # OllamaChatCompletionClientを使用
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
        )

    if provider == "lmstudio":
        return OpenAIChatCompletionClient(
            model=model_name,
            base_url=lmstudio_url,
            api_key="lm-studio",
            model_info=ModelInfo(
                vision=False,
                function_calling=False,
                json_output=True,
                family="unknown",
                structured_output=False,
            ),
        )

    raise ValueError(
        f"未対応のプロバイダー: {provider}。"
        "openai / gemini / ollama / lmstudio のいずれかを指定してください。"
    )
