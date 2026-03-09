from autogen_agentchat.messages import TextMessage

from src.agents.discussion import RateLimitedAssistantAgent


def _build_agent(max_context_messages: int) -> RateLimitedAssistantAgent:
    agent = object.__new__(RateLimitedAssistantAgent)
    agent._max_context_messages = max_context_messages
    return agent


def _build_messages(count: int) -> list[TextMessage]:
    return [
        TextMessage(content=f"message-{index}", source=f"source-{index}")
        for index in range(count)
    ]


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
