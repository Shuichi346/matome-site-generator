from pathlib import Path

import pytest
from autogen_agentchat.messages import MultiModalMessage, TextMessage
from autogen_core import Image
from PIL import Image as PILImage

from src import app
from src.agents.discussion import CHAT_PATTERN_ROUND_ROBIN
from src.agents.image_analyzer import (
    ImageAnalysisError,
    analyze_image_for_discussion,
)
from src.agents.persona import Persona
from src.utils.rate_limiter import RateLimiter


def _write_test_image(tmp_path: Path) -> Path:
    image_path = tmp_path / "test.png"
    image = PILImage.new("RGB", (2, 2), color=(255, 0, 0))
    image.save(image_path)
    return image_path


@pytest.mark.asyncio
async def test_analyze_image_uses_multimodal_input(monkeypatch, tmp_path) -> None:
    image_path = _write_test_image(tmp_path)
    captured: dict[str, object] = {}

    class DummyClient:
        async def close(self) -> None:
            return None

    class DummyAgent:
        def __init__(self, **kwargs) -> None:
            captured["agent_kwargs"] = kwargs

        async def run(self, task):
            captured["task"] = task
            return type(
                "Result",
                (),
                {
                    "messages": [
                        task,
                        TextMessage(
                            content="画像の分析結果です",
                            source="image_analyzer",
                        ),
                    ]
                },
            )()

    monkeypatch.setattr(
        "src.agents.image_analyzer.provider_supports_vision",
        lambda provider, settings=None: True,
    )
    monkeypatch.setattr(
        "src.agents.image_analyzer.create_model_client",
        lambda **_kwargs: DummyClient(),
    )
    monkeypatch.setattr("src.agents.image_analyzer.AssistantAgent", DummyAgent)

    result = await analyze_image_for_discussion(
        image_path=image_path,
        theme="テーマ",
        context="補足",
        provider="gemini",
        model_name="model",
        rate_limiter=RateLimiter(wait_seconds=0),
    )

    assert result == "画像の分析結果です"
    assert isinstance(captured["task"], MultiModalMessage)
    assert any(
        isinstance(part, Image)
        for part in captured["task"].content
    )


@pytest.mark.asyncio
async def test_analyze_image_requires_vision_model(monkeypatch, tmp_path) -> None:
    image_path = _write_test_image(tmp_path)
    monkeypatch.setattr(
        "src.agents.image_analyzer.provider_supports_vision",
        lambda provider, settings=None: False,
    )

    with pytest.raises(ImageAnalysisError) as exc_info:
        await analyze_image_for_discussion(
            image_path=image_path,
            theme="テーマ",
            context="補足",
            provider="ollama",
            model_name="model",
            rate_limiter=RateLimiter(wait_seconds=0),
        )

    assert "vision 対応モデル" in str(exc_info.value)


@pytest.mark.asyncio
async def test_image_analysis_result_is_added_to_discussion_context(
    monkeypatch,
    tmp_path,
) -> None:
    image_path = _write_test_image(tmp_path)
    captured_theme: dict[str, str] = {}

    monkeypatch.setattr(app, "_save_ui_settings", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "load_settings", lambda: {})
    monkeypatch.setattr(
        app,
        "generate_personas",
        lambda *_args, **_kwargs: [
            Persona(
                name="名無しさん",
                display_id="agentid1",
                personality="冷静",
                speech_style="通常",
                stance="中立",
            )
        ],
    )
    monkeypatch.setattr(app, "build_discussion_agents", lambda **_kwargs: ["agent"])

    async def close_agents(_agents) -> None:
        return None

    async def generate_thread_title(**_kwargs) -> str:
        return "テストスレ"

    async def analyze_image(**_kwargs) -> str:
        return "画像の解析結果"

    async def run_discussion_stream(**kwargs):
        captured_theme["theme"] = kwargs["theme"]
        yield TextMessage(content="最初のレス", source="agent_0_agentid1")
        app._request_cancel()

    monkeypatch.setattr(app, "close_discussion_agents", close_agents)
    monkeypatch.setattr(app, "generate_thread_title", generate_thread_title)
    monkeypatch.setattr(app, "analyze_image_for_discussion", analyze_image)
    monkeypatch.setattr(app, "run_discussion_stream", run_discussion_stream)

    outputs = []
    async for item in app.generate_matome_streaming(
        theme="画像付きテーマ",
        context="補足",
        tones=["通常"],
        conv_count=5,
        participant_count=1,
        image_path=str(image_path),
        file_path=None,
        disc_provider="gemini",
        disc_model="disc-model",
        sum_provider="gemini",
        sum_model="sum-model",
        wait_time_sec=0,
        ollama_url="http://localhost:11434",
        openrouter_url="https://openrouter.ai/api/v1",
        custom_openai_url="",
        custom_openai_api_key="",
        ref_urls="",
        search_keywords="",
        max_search_results=3,
        max_url_content_length=2000,
        search_content_mode="snippet",
        max_context_messages=10,
        disc_mapping={"gemini": "disc-model"},
        sum_mapping={"gemini": "sum-model"},
        ollama_disc_think="OFF",
        ollama_sum_think="OFF",
        chat_pattern=CHAT_PATTERN_ROUND_ROBIN,
    ):
        outputs.append(item)

    assert outputs[0][0] == "画像を解析中..."
    assert "【添付画像の内容】\n画像の解析結果" in captured_theme["theme"]
