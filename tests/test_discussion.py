from autogen_agentchat.messages import TextMessage

from src.agents.discussion import (
    RateLimitedAssistantAgent,
    _stamp_res_numbers,
)


def _build_agent(max_context_messages: int) -> RateLimitedAssistantAgent:
    agent = object.__new__(RateLimitedAssistantAgent)
    agent._max_context_messages = max_context_messages
    agent._message_history = []
    agent._name = "agent_test"
    return agent


def _build_messages(count: int) -> list[TextMessage]:
    return [
        TextMessage(content=f"message-{index}", source=f"source-{index}")
        for index in range(count)
    ]


# ========================================
# _trim_messages のテスト
# ========================================


def test_trim_messages_without_limit() -> None:
    messages = _build_messages(4)
    agent = _build_agent(0)

    trimmed = agent._trim_messages(messages)

    assert list(trimmed) == messages


def test_trim_messages_with_one_keeps_first_only() -> None:
    messages = _build_messages(4)
    agent = _build_agent(1)

    trimmed = list(agent._trim_messages(messages))

    assert trimmed == [messages[0]]


def test_trim_messages_with_two_keeps_first_and_latest() -> None:
    messages = _build_messages(5)
    agent = _build_agent(2)

    trimmed = list(agent._trim_messages(messages))

    assert trimmed == [messages[0], messages[-1]]


def test_trim_messages_does_not_duplicate_first_message() -> None:
    messages = _build_messages(5)
    agent = _build_agent(3)

    trimmed = list(agent._trim_messages(messages))

    assert trimmed == [messages[0], messages[-2], messages[-1]]
    assert trimmed.count(messages[0]) == 1


# ========================================
# _stamp_res_numbers のテスト
# ========================================


def test_stamp_res_numbers_basic() -> None:
    """各メッセージに実際のレス番号が付与される"""
    messages = _build_messages(3)

    stamped = _stamp_res_numbers(messages)

    assert len(stamped) == 3
    assert stamped[0].content == "[現在のレス番号: >>1]\nmessage-0"
    assert stamped[1].content == "[現在のレス番号: >>2]\nmessage-1"
    assert stamped[2].content == "[現在のレス番号: >>3]\nmessage-2"
    assert stamped[0].source == "source-0"
    assert stamped[2].source == "source-2"


def test_stamp_res_numbers_empty() -> None:
    """空リストに対しても正常動作する"""
    stamped = _stamp_res_numbers([])
    assert stamped == []


# ========================================
# _prepare_messages のテスト（番号付与→トリミング）
# ========================================


def test_prepare_preserves_real_numbers_after_trim() -> None:
    """トリミングしても実際のレス番号が保持される

    5件中 max_context_messages=3 → [0, 3, 4] が残る。
    レス番号は先に振るので >>1, >>4, >>5 になる。
    """
    messages = _build_messages(5)
    agent = _build_agent(3)

    prepared = agent._prepare_messages(messages)

    assert len(prepared) == 3
    assert prepared[0].content == "[現在のレス番号: >>1]\nmessage-0"
    assert prepared[1].content == "[現在のレス番号: >>4]\nmessage-3"
    assert prepared[2].content == "[現在のレス番号: >>5]\nmessage-4"


def test_prepare_no_trim_all_numbers_sequential() -> None:
    """トリミングなし(0)の場合、全件に連番が付く"""
    messages = _build_messages(4)
    agent = _build_agent(0)

    prepared = agent._prepare_messages(messages)

    assert len(prepared) == 4
    assert prepared[0].content == "[現在のレス番号: >>1]\nmessage-0"
    assert prepared[1].content == "[現在のレス番号: >>2]\nmessage-1"
    assert prepared[2].content == "[現在のレス番号: >>3]\nmessage-2"
    assert prepared[3].content == "[現在のレス番号: >>4]\nmessage-3"


def test_prepare_large_trim_keeps_real_numbers() -> None:
    """50件中 max_context_messages=3 でも実際のレス番号が正しい"""
    messages = _build_messages(50)
    agent = _build_agent(3)

    prepared = agent._prepare_messages(messages)

    assert len(prepared) == 3
    assert prepared[0].content == "[現在のレス番号: >>1]\nmessage-0"
    assert prepared[1].content == "[現在のレス番号: >>49]\nmessage-48"
    assert prepared[2].content == "[現在のレス番号: >>50]\nmessage-49"


# ========================================
# 累積履歴のテスト
# ========================================


def test_prepare_history_messages_keeps_global_numbers_across_turns() -> None:
    agent = _build_agent(0)

    agent._remember_messages([
        TextMessage(content="task", source="user"),
    ])
    agent._remember_response(
        TextMessage(content="self-reply", source="agent_test")
    )
    agent._remember_messages([
        TextMessage(content="other-1", source="agent_1"),
        TextMessage(content="other-2", source="agent_2"),
        TextMessage(content="other-3", source="agent_3"),
        TextMessage(content="other-4", source="agent_4"),
    ])

    prepared = list(agent._prepare_history_messages())

    assert prepared[0].content == "[現在のレス番号: >>1]\ntask"
    assert prepared[1].content == "[現在のレス番号: >>2]\nself-reply"
    assert prepared[2].content == "[現在のレス番号: >>3]\nother-1"
    assert prepared[3].content == "[現在のレス番号: >>4]\nother-2"
    assert prepared[4].content == "[現在のレス番号: >>5]\nother-3"
    assert prepared[5].content == "[現在のレス番号: >>6]\nother-4"


def test_prepare_history_messages_with_trim_keeps_real_numbers() -> None:
    agent = _build_agent(3)

    agent._remember_messages([
        TextMessage(content="task", source="user"),
    ])
    agent._remember_response(
        TextMessage(content="self-reply", source="agent_test")
    )
    agent._remember_messages([
        TextMessage(content="other-1", source="agent_1"),
        TextMessage(content="other-2", source="agent_2"),
        TextMessage(content="other-3", source="agent_3"),
    ])

    prepared = list(agent._prepare_history_messages())

    assert len(prepared) == 3
    assert prepared[0].content == "[現在のレス番号: >>1]\ntask"
    assert prepared[1].content == "[現在のレス番号: >>4]\nother-2"
    assert prepared[2].content == "[現在のレス番号: >>5]\nother-3"


def test_on_reset_clears_message_history() -> None:
    agent = _build_agent(3)

    agent._remember_messages([
        TextMessage(content="task", source="user"),
        TextMessage(content="other", source="agent_1"),
    ])

    assert len(agent._message_history) == 2

    agent._message_history.clear()

    assert agent._message_history == []
