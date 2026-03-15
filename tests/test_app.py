from pathlib import Path

import pytest
from autogen_agentchat.messages import TextMessage

from src import app
from src.agents.discussion import CHAT_PATTERN_ROUND_ROBIN
from src.agents.persona import Persona


def _base_kwargs() -> dict[str, object]:
    return {
        "theme": "テーマ https://example.com/theme",
        "context": "補足 https://example.com/context",
        "tones": ["通常"],
        "conv_count": 5,
        "participant_count": 1,
        "image_path": None,
        "file_path": None,
        "disc_provider": "gemini",
        "disc_model": "disc-model",
        "sum_provider": "gemini",
        "sum_model": "sum-model",
        "wait_time_sec": 0,
        "ollama_url": "http://localhost:11434",
        "openrouter_url": "https://openrouter.ai/api/v1",
        "custom_openai_url": "",
        "custom_openai_api_key": "",
        "ref_urls": "https://example.com/ref\nhttps://example.com/theme",
        "search_keywords": "",
        "max_search_results": 3,
        "max_url_content_length": 2000,
        "search_content_mode": "snippet",
        "max_context_messages": 10,
        "disc_mapping": {"gemini": "disc-model"},
        "sum_mapping": {"gemini": "sum-model"},
        "ollama_disc_think": "OFF",
        "ollama_sum_think": "OFF",
        "chat_pattern": CHAT_PATTERN_ROUND_ROBIN,
    }


def _persona() -> Persona:
    return Persona(
        name="名無しさん",
        display_id="agentid1",
        personality="冷静",
        speech_style="通常",
        stance="中立",
    )


async def _collect_outputs(async_gen, on_yield=None) -> list[tuple]:
    outputs: list[tuple] = []
    async for item in async_gen:
        outputs.append(item)
        if on_yield is not None:
            on_yield(item)
    return outputs


def _patch_common(monkeypatch) -> None:
    monkeypatch.setattr(app, "_save_ui_settings", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "load_settings", lambda: {})
    monkeypatch.setattr(app, "generate_personas", lambda *_args, **_kwargs: [_persona()])
    monkeypatch.setattr(app, "build_discussion_agents", lambda **_kwargs: ["agent"])

    async def close_agents(_agents) -> None:
        return None

    monkeypatch.setattr(app, "close_discussion_agents", close_agents)


@pytest.mark.asyncio
async def test_user_input_urls_are_always_full_in_snippet_mode(monkeypatch) -> None:
    _patch_common(monkeypatch)
    calls: dict[str, object] = {}

    async def fetch_multiple_urls(urls, max_length):
        calls["urls"] = list(urls)
        calls["max_length"] = max_length
        return [{"url": url, "title": url, "content": "本文", "error": ""} for url in urls]

    def format_url_results_as_context(results, snippet_only=False):
        calls["results"] = list(results)
        calls["snippet_only"] = snippet_only
        return "\n【参考URLの内容】\n本文"

    monkeypatch.setattr(app, "fetch_multiple_urls", fetch_multiple_urls)
    monkeypatch.setattr(app, "format_url_results_as_context", format_url_results_as_context)
    monkeypatch.setattr(
        app,
        "generate_personas",
        lambda *_args, **_kwargs: (
            app._request_cancel(),
            [_persona()],
        )[1],
    )

    outputs = await _collect_outputs(
        app.generate_matome_streaming(**_base_kwargs())
    )

    assert calls["urls"] == [
        "https://example.com/theme",
        "https://example.com/context",
        "https://example.com/ref",
    ]
    assert calls["snippet_only"] is False
    assert outputs[-1][0] == "中止しました。出力は生成していません。"


@pytest.mark.asyncio
async def test_cancel_before_any_post_stops_without_outputs(monkeypatch) -> None:
    _patch_common(monkeypatch)
    summarizer_calls = 0
    export_calls = 0

    async def generate_thread_title(**_kwargs) -> str:
        app._request_cancel()
        return "テストスレ"

    async def run_summarizer(**_kwargs):
        nonlocal summarizer_calls
        summarizer_calls += 1
        return {}

    def generate_export_files(**_kwargs):
        nonlocal export_calls
        export_calls += 1
        return Path("/tmp/never.zip")

    monkeypatch.setattr(app, "generate_thread_title", generate_thread_title)
    monkeypatch.setattr(app, "run_summarizer", run_summarizer)
    monkeypatch.setattr(app, "_generate_export_files", generate_export_files)

    outputs = await _collect_outputs(
        app.generate_matome_streaming(**_base_kwargs())
    )

    assert outputs[-1][0] == "中止しました。出力は生成していません。"
    assert outputs[-1][4] is None
    assert summarizer_calls == 0
    assert export_calls == 0


@pytest.mark.asyncio
async def test_cancel_during_discussion_does_not_start_summary(monkeypatch) -> None:
    _patch_common(monkeypatch)
    summarizer_calls = 0

    async def generate_thread_title(**_kwargs) -> str:
        return "テストスレ"

    async def run_discussion_stream(**_kwargs):
        yield TextMessage(content="最初のレス", source="agent_0_agentid1")

    async def run_summarizer(**_kwargs):
        nonlocal summarizer_calls
        summarizer_calls += 1
        return {}

    monkeypatch.setattr(app, "generate_thread_title", generate_thread_title)
    monkeypatch.setattr(app, "run_discussion_stream", run_discussion_stream)
    monkeypatch.setattr(app, "run_summarizer", run_summarizer)

    def cancel_on_discussion(item: tuple) -> None:
        if "議論を実行中..." in item[0]:
            message = app._request_cancel()
            assert "現在のレス生成" in message

    outputs = await _collect_outputs(
        app.generate_matome_streaming(**_base_kwargs()),
        on_yield=cancel_on_discussion,
    )

    assert outputs[-1][0] == "中止しました。スレッドと生ログのみ表示しています。"
    assert outputs[-1][2] == ""
    assert outputs[-1][4] is None
    assert summarizer_calls == 0


@pytest.mark.asyncio
async def test_cancel_before_summary_does_not_start_new_step(monkeypatch) -> None:
    _patch_common(monkeypatch)
    summarizer_calls = 0
    cancel_messages: list[str] = []

    async def generate_thread_title(**_kwargs) -> str:
        return "テストスレ"

    async def run_discussion_stream(**_kwargs):
        yield TextMessage(content="最初のレス", source="agent_0_agentid1")
        cancel_messages.append(app._request_cancel())

    async def run_summarizer(**_kwargs):
        nonlocal summarizer_calls
        summarizer_calls += 1
        return {}

    monkeypatch.setattr(app, "generate_thread_title", generate_thread_title)
    monkeypatch.setattr(app, "run_discussion_stream", run_discussion_stream)
    monkeypatch.setattr(app, "run_summarizer", run_summarizer)

    outputs = await _collect_outputs(
        app.generate_matome_streaming(**_base_kwargs())
    )

    assert cancel_messages
    assert "現在のレス生成" in cancel_messages[0]
    assert outputs[-1][0] == "中止しました。スレッドと生ログのみ表示しています。"
    assert summarizer_calls == 0


@pytest.mark.asyncio
async def test_cancel_during_summary_skips_zip_generation(monkeypatch) -> None:
    _patch_common(monkeypatch)
    export_calls = 0
    cancel_messages: list[str] = []

    async def generate_thread_title(**_kwargs) -> str:
        return "テストスレ"

    async def run_discussion_stream(**_kwargs):
        yield TextMessage(content="最初のレス", source="agent_0_agentid1")

    async def run_summarizer(**_kwargs):
        cancel_messages.append(app._request_cancel())
        return {
            "title": "まとめ",
            "category": "議論",
            "thread_comments": [
                {
                    "number": 1,
                    "name": "名無しさん",
                    "id": "agentid1",
                    "content": "最初のレス",
                    "is_highlighted": False,
                    "highlight_color": None,
                }
            ],
            "editor_comment": "導入",
            "reactions_summary": "反応",
        }

    def generate_export_files(**_kwargs):
        nonlocal export_calls
        export_calls += 1
        return Path("/tmp/never.zip")

    monkeypatch.setattr(app, "generate_thread_title", generate_thread_title)
    monkeypatch.setattr(app, "run_discussion_stream", run_discussion_stream)
    monkeypatch.setattr(app, "run_summarizer", run_summarizer)
    monkeypatch.setattr(app, "_generate_export_files", generate_export_files)

    outputs = await _collect_outputs(
        app.generate_matome_streaming(**_base_kwargs())
    )

    assert cancel_messages
    assert "まとめ生成" in cancel_messages[0]
    assert outputs[-1][0] == (
        "中止しました。まとめ表示まで生成しましたが、"
        "出力ファイルとZIPは生成していません。"
    )
    assert outputs[-1][2] != ""
    assert outputs[-1][4] is None
    assert export_calls == 0
