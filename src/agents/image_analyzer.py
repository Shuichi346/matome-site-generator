"""添付画像を議論用に解析するモジュール"""

import inspect
from pathlib import Path
from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import MultiModalMessage, TextMessage
from autogen_core import Image

from src.models.client_factory import (
    create_model_client,
    provider_supports_vision,
)
from src.utils.rate_limiter import RateLimiter


class ImageAnalysisError(RuntimeError):
    """画像解析に失敗したことを示す例外"""


IMAGE_ANALYZER_SYSTEM_PROMPT = """あなたは匿名掲示板の議論を始める前に、
添付画像を読み解いて論点を整理する担当です。
出力は日本語のプレーンテキストのみで、600〜1200文字程度に収めてください。
次の順で簡潔に述べてください。

1. 画像に写っている主要な物
2. 読み取れる文字
3. 数字・表・UI・グラフがあればその内容
4. 雰囲気や状況
5. 不確かな点
6. 掲示板で議論になりそうな論点

不確かな点は「不確か」と明記してください。
見えない内容を断定しないでください。
JSONや箇条書き記号は必須ではありませんが、読みやすく整理してください。
"""


async def _close_model_client(client: Any) -> None:
    """モデルクライアントを安全に閉じる"""
    close_method = getattr(client, "close", None)
    if not callable(close_method):
        return

    result = close_method()
    if inspect.isawaitable(result):
        await result


def _normalize_analysis_text(text: str) -> str:
    """画像解析結果を整形する"""
    normalized = text.strip()
    if not normalized:
        raise ImageAnalysisError(
            "現在の provider / model 設定では画像解析に失敗しました。"
            "vision 対応モデルを選んでください"
        )
    if len(normalized) > 1200:
        return normalized[:1200].rstrip() + "…"
    return normalized


async def analyze_image_for_discussion(
    image_path: str | Path,
    theme: str,
    context: str,
    provider: str,
    model_name: str,
    rate_limiter: RateLimiter,
    settings: dict[str, Any] | None = None,
    ollama_url: str = "http://localhost:11434",
    openrouter_url: str = "",
    custom_openai_url: str = "",
    custom_openai_api_key: str = "",
    ollama_think: bool | None = None,
) -> str:
    """添付画像をvision対応モデルで解析し、議論向けメモを返す"""
    if not provider_supports_vision(provider, settings):
        raise ImageAnalysisError(
            "添付画像を使うには vision 対応モデルが必要です"
        )

    image_file = Path(image_path)
    if not image_file.exists():
        raise ImageAnalysisError("添付画像の読み込みに失敗しました")

    try:
        image = Image.from_file(image_file)
    except Exception as exc:
        raise ImageAnalysisError("添付画像の読み込みに失敗しました") from exc

    client = create_model_client(
        provider=provider,
        model_name=model_name,
        settings=settings,
        ollama_url=ollama_url,
        openrouter_url=openrouter_url,
        custom_openai_url=custom_openai_url,
        custom_openai_api_key=custom_openai_api_key,
        ollama_think=ollama_think,
    )

    try:
        agent = AssistantAgent(
            name="image_analyzer",
            model_client=client,
            system_message=IMAGE_ANALYZER_SYSTEM_PROMPT,
        )

        prompt_parts: list[str | Image] = [
            "以下の添付画像を解析し、議論用メモを作成してください。\n",
            f"テーマ: {theme.strip() or '未設定'}\n",
            f"補足: {context.strip() or 'なし'}\n",
            (
                "画像に書かれた文字、数値、UI、表、グラフ、"
                "雰囲気、論点候補を見落とさずにまとめてください。\n"
            ),
            image,
        ]

        await rate_limiter.wait()
        result = await agent.run(
            task=MultiModalMessage(
                source="user",
                content=prompt_parts,
            )
        )

        for msg in reversed(result.messages):
            if isinstance(msg, TextMessage) and msg.source != "user":
                return _normalize_analysis_text(msg.content)
    except RuntimeError:
        raise
    except ImageAnalysisError:
        raise
    except Exception as exc:
        raise ImageAnalysisError(
            "現在の provider / model 設定では画像解析に失敗しました。"
            "vision 対応モデルを選んでください"
        ) from exc
    finally:
        await _close_model_client(client)

    raise ImageAnalysisError(
        "現在の provider / model 設定では画像解析に失敗しました。"
        "vision 対応モデルを選んでください"
    )
