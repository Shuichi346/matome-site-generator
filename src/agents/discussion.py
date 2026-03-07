"""議論エージェント群の構築と実行モジュール

ペルソナ群からAutoGen AssistantAgentを生成し、
RoundRobinGroupChatで議論を実行する。
ストリーミングモードでは1レスずつ非同期に返す。
"""

from typing import Any, AsyncGenerator, Sequence

from autogen_agentchat.agents import AssistantAgent, BaseChatAgent
from autogen_agentchat.base import Response, TaskResult
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.messages import (
    BaseAgentEvent,
    BaseChatMessage,
    TextMessage,
)
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core import CancellationToken

from src.agents.persona import Persona, build_system_prompt
from src.models.client_factory import create_model_client
from src.utils.rate_limiter import RateLimiter


class RateLimitedAssistantAgent(BaseChatAgent):
    """レートリミット付きのAssistantAgent

    内部にAssistantAgentを保持し、
    応答前にレートリミッターで待機する。
    """

    def __init__(
        self,
        name: str,
        rate_limiter: RateLimiter,
        model_client: Any,
        system_message: str,
        description: str = "レートリミット付きアシスタント",
    ) -> None:
        super().__init__(name=name, description=description)
        self._rate_limiter = rate_limiter
        self._inner_agent = AssistantAgent(
            name=f"_inner_{name}",
            model_client=model_client,
            system_message=system_message,
        )

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TextMessage,)

    async def on_messages(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> Response:
        """メッセージを受け取り、レートリミット後に応答する"""
        await self._rate_limiter.wait()
        inner_response = await self._inner_agent.on_messages(
            messages, cancellation_token
        )
        chat_msg = inner_response.chat_message
        if isinstance(chat_msg, TextMessage):
            rewritten = TextMessage(
                content=chat_msg.content,
                source=self.name,
                models_usage=chat_msg.models_usage,
            )
            return Response(
                chat_message=rewritten,
                inner_messages=inner_response.inner_messages,
            )
        return inner_response

    async def on_messages_stream(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        """ストリーミング応答（レートリミット付き）"""
        await self._rate_limiter.wait()
        response = await self._inner_agent.on_messages(
            messages, cancellation_token
        )
        chat_msg = response.chat_message
        if isinstance(chat_msg, TextMessage):
            rewritten = TextMessage(
                content=chat_msg.content,
                source=self.name,
                models_usage=chat_msg.models_usage,
            )
            yield Response(
                chat_message=rewritten,
                inner_messages=response.inner_messages,
            )
        else:
            yield response

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        """エージェントをリセットする"""
        await self._inner_agent.on_reset(cancellation_token)


def build_discussion_agents(
    personas: list[Persona],
    theme: str,
    context: str,
    tones: list[str],
    provider: str,
    model_name: str,
    rate_limiter: RateLimiter,
    settings: dict[str, Any] | None = None,
    ollama_url: str = "http://localhost:11434",
    lmstudio_url: str = "http://localhost:1234/v1",
) -> list[RateLimitedAssistantAgent]:
    """ペルソナ群から議論用エージェントを構築する

    Args:
        personas: ペルソナのリスト
        theme: 議論テーマ
        context: 補足情報
        tones: 議論トーン
        provider: LLMプロバイダー
        model_name: モデル名
        rate_limiter: レートリミッターインスタンス
        settings: 設定辞書
        ollama_url: OllamaサーバーURL
        lmstudio_url: LM StudioサーバーURL

    Returns:
        エージェントのリスト
    """
    agents: list[RateLimitedAssistantAgent] = []

    for i, persona in enumerate(personas):
        client = create_model_client(
            provider=provider,
            model_name=model_name,
            settings=settings,
            ollama_url=ollama_url,
            lmstudio_url=lmstudio_url,
        )
        system_prompt = build_system_prompt(persona, theme, context, tones)
        agent = RateLimitedAssistantAgent(
            name=f"agent_{i}_{persona.display_id}",
            rate_limiter=rate_limiter,
            model_client=client,
            system_message=system_prompt,
            description=f"{persona.name} (ID:{persona.display_id})",
        )
        agents.append(agent)

    return agents


async def run_discussion(
    agents: list[RateLimitedAssistantAgent],
    thread_title: str,
    theme: str,
    conversation_count: int,
) -> TaskResult:
    """RoundRobinGroupChatで議論を実行する（一括完了版）

    Args:
        agents: 議論用エージェントのリスト
        thread_title: スレッドタイトル
        theme: テーマ説明
        conversation_count: 会話数

    Returns:
        TaskResult（全メッセージを含む）
    """
    termination = MaxMessageTermination(max_messages=conversation_count)
    team = RoundRobinGroupChat(
        participants=agents,
        termination_condition=termination,
    )

    task_message = f"""スレタイ: {thread_title}

{theme}

議論よろしく"""

    result = await team.run(task=task_message)
    return result


async def run_discussion_stream(
    agents: list[RateLimitedAssistantAgent],
    thread_title: str,
    theme: str,
    conversation_count: int,
) -> AsyncGenerator[TextMessage | TaskResult, None]:
    """RoundRobinGroupChatで議論を実行する（ストリーミング版）

    メッセージが生成されるたびに1件ずつyieldする。
    最後にTaskResultをyieldする。

    Args:
        agents: 議論用エージェントのリスト
        thread_title: スレッドタイトル
        theme: テーマ説明
        conversation_count: 会話数

    Yields:
        TextMessage: 各レスのメッセージ
        TaskResult: 最終結果（最後の1件）
    """
    termination = MaxMessageTermination(max_messages=conversation_count)
    team = RoundRobinGroupChat(
        participants=agents,
        termination_condition=termination,
    )

    task_message = f"""スレタイ: {thread_title}

{theme}

議論よろしく"""

    async for item in team.run_stream(task=task_message):
        if isinstance(item, TaskResult):
            yield item
        elif isinstance(item, TextMessage):
            yield item
        # BaseAgentEvent等はスキップ
