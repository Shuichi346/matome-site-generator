"""議論エージェント群の構築と実行モジュール

ペルソナ群からAutoGen AssistantAgentを生成し、
RoundRobinGroupChatで議論を実行する。
ストリーミングモードでは1レスずつ非同期に返す。
レートリミットエラー(429)発生時はユーザーに通知して停止する。
ユーザー操作による停止はExternalTerminationを使い、
実行中のHTTP通信を壊さず穏当に終了させる。
"""

import asyncio
import inspect
from typing import Any, AsyncGenerator, Sequence

from autogen_agentchat.agents import AssistantAgent, BaseChatAgent
from autogen_agentchat.base import Response, TaskResult
from autogen_agentchat.conditions import (
    ExternalTermination,
    MaxMessageTermination,
)
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


class RateLimitError(Exception):
    """APIレートリミットに達したことを示す例外"""

    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.original_error = original_error


def _is_rate_limit_error(exc: Exception) -> bool:
    """例外がレートリミット関連かどうかを判定する"""
    exc_type_name = type(exc).__name__
    if exc_type_name == "RateLimitError":
        return True

    if hasattr(exc, "status_code") and getattr(exc, "status_code", 0) == 429:
        return True

    if hasattr(exc, "response"):
        response = getattr(exc, "response", None)
        if response is not None and hasattr(response, "status_code"):
            if response.status_code == 429:
                return True

    message = str(exc).lower()
    if "429" in message and ("rate" in message or "limit" in message):
        return True

    return False


def _extract_rate_limit_detail(exc: Exception) -> str:
    """レートリミットエラーからユーザー向け詳細を抽出する"""
    message = str(exc)
    if "metadata" in message and "raw" in message:
        try:
            import json
            import re

            match = re.search(r"\{.*\}", message, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                raw = data.get("error", {}).get("metadata", {}).get(
                    "raw", ""
                )
                if raw:
                    return raw
        except Exception:
            pass
    return message


def _build_termination_condition(
    conversation_count: int,
    external_termination: ExternalTermination | None,
):
    """停止条件を構築する"""
    termination = MaxMessageTermination(max_messages=conversation_count)
    if external_termination is not None:
        termination = termination | external_termination
    return termination


class RateLimitedAssistantAgent(BaseChatAgent):
    """レートリミット付きのAssistantAgent"""

    def __init__(
        self,
        name: str,
        rate_limiter: RateLimiter,
        model_client: Any,
        system_message: str,
        description: str = "レートリミット付きアシスタント",
        max_context_messages: int = 0,
    ) -> None:
        super().__init__(name=name, description=description)
        self._rate_limiter = rate_limiter
        self._model_client = model_client
        self._max_context_messages = max_context_messages
        self._inner_agent = AssistantAgent(
            name=f"_inner_{name}",
            model_client=model_client,
            system_message=system_message,
        )

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TextMessage,)

    def _rewrite_text_message(self, message: TextMessage) -> TextMessage:
        """内部エージェントの送信者名を外側の名前に差し替える"""
        return TextMessage(
            content=message.content,
            source=self.name,
            models_usage=message.models_usage,
        )

    def _trim_messages(
        self,
        messages: Sequence[BaseChatMessage],
    ) -> Sequence[BaseChatMessage]:
        """会話履歴を最新N件に制限する

        最初のメッセージ（テーマ・参考情報）は常に含め、
        残りは直近の max_context_messages - 1 件を保持する。
        0以下の場合は制限しない。
        """
        if self._max_context_messages <= 0:
            return messages
        if len(messages) <= self._max_context_messages:
            return messages
        first_msg = messages[0]
        recent = messages[-(self._max_context_messages - 1):]
        return [first_msg] + list(recent)

    async def on_messages(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> Response:
        """メッセージを受け取り、レートリミット後に応答する"""
        await self._rate_limiter.wait()
        trimmed = self._trim_messages(messages)
        try:
            inner_response = await self._inner_agent.on_messages(
                trimmed,
                cancellation_token,
            )
        except Exception as exc:
            if _is_rate_limit_error(exc):
                detail = _extract_rate_limit_detail(exc)
                raise RateLimitError(
                    f"APIレートリミットに達しました: {detail}",
                    original_error=exc,
                ) from exc
            raise

        chat_message = inner_response.chat_message
        if isinstance(chat_message, TextMessage):
            return Response(
                chat_message=self._rewrite_text_message(chat_message),
                inner_messages=inner_response.inner_messages,
            )

        return inner_response

    async def on_messages_stream(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> AsyncGenerator[
        BaseAgentEvent | BaseChatMessage | Response,
        None,
    ]:
        """ストリーミング応答（レートリミット付き）"""
        await self._rate_limiter.wait()
        trimmed = self._trim_messages(messages)
        try:
            async for item in self._inner_agent.on_messages_stream(
                trimmed,
                cancellation_token,
            ):
                if isinstance(item, Response):
                    chat_message = item.chat_message
                    if isinstance(chat_message, TextMessage):
                        yield Response(
                            chat_message=self._rewrite_text_message(
                                chat_message
                            ),
                            inner_messages=item.inner_messages,
                        )
                    else:
                        yield item
                elif isinstance(item, TextMessage):
                    yield self._rewrite_text_message(item)
                else:
                    yield item
        except Exception as exc:
            if _is_rate_limit_error(exc):
                detail = _extract_rate_limit_detail(exc)
                raise RateLimitError(
                    f"APIレートリミットに達しました: {detail}",
                    original_error=exc,
                ) from exc
            raise

    async def on_reset(
        self,
        cancellation_token: CancellationToken,
    ) -> None:
        """エージェントをリセットする"""
        await self._inner_agent.on_reset(cancellation_token)

    async def close(self) -> None:
        """保持しているモデルクライアントを閉じる"""
        close_method = getattr(self._model_client, "close", None)
        if not callable(close_method):
            return

        result = close_method()
        if inspect.isawaitable(result):
            await result


async def close_discussion_agents(
    agents: Sequence[RateLimitedAssistantAgent],
) -> None:
    """議論用エージェント群のクライアントを閉じる"""
    if not agents:
        return

    await asyncio.gather(
        *(agent.close() for agent in agents),
        return_exceptions=True,
    )


def build_discussion_agents(
    personas: list[Persona],
    theme: str,
    context: str,
    tones: list[str],
    provider: str,
    model_name: str,
    rate_limiter: RateLimiter,
    settings: dict[str, Any] | None = None,
    max_context_messages: int = 0,
    ollama_url: str = "http://localhost:11434",
    openrouter_url: str = "",
    custom_openai_url: str = "",
    custom_openai_api_key: str = "",
    ollama_think: bool | None = None,
) -> list[RateLimitedAssistantAgent]:
    """ペルソナ群から議論用エージェントを構築する"""
    agents: list[RateLimitedAssistantAgent] = []

    for i, persona in enumerate(personas):
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
        system_prompt = build_system_prompt(persona, theme, context, tones)
        agent = RateLimitedAssistantAgent(
            name=f"agent_{i}_{persona.display_id}",
            rate_limiter=rate_limiter,
            model_client=client,
            system_message=system_prompt,
            description=f"{persona.name} (ID:{persona.display_id})",
            max_context_messages=max_context_messages,
        )
        agents.append(agent)

    return agents


async def run_discussion(
    agents: list[RateLimitedAssistantAgent],
    thread_title: str,
    theme: str,
    conversation_count: int,
    external_termination: ExternalTermination | None = None,
    cancellation_token: CancellationToken | None = None,
) -> TaskResult:
    """RoundRobinGroupChatで議論を実行する（一括完了版）"""
    termination = _build_termination_condition(
        conversation_count,
        external_termination,
    )
    team = RoundRobinGroupChat(
        participants=agents,
        termination_condition=termination,
    )

    task_message = f"""スレタイ: {thread_title}

{theme}

議論よろしく"""

    result = await team.run(
        task=task_message,
        cancellation_token=cancellation_token,
    )
    return result


async def run_discussion_stream(
    agents: list[RateLimitedAssistantAgent],
    thread_title: str,
    theme: str,
    conversation_count: int,
    external_termination: ExternalTermination | None = None,
    cancellation_token: CancellationToken | None = None,
) -> AsyncGenerator[TextMessage | TaskResult, None]:
    """RoundRobinGroupChatで議論を実行する（ストリーミング版）"""
    termination = _build_termination_condition(
        conversation_count,
        external_termination,
    )
    team = RoundRobinGroupChat(
        participants=agents,
        termination_condition=termination,
    )

    task_message = f"""スレタイ: {thread_title}

{theme}

議論よろしく"""

    async for item in team.run_stream(
        task=task_message,
        cancellation_token=cancellation_token,
    ):
        if isinstance(item, TaskResult):
            yield item
        elif isinstance(item, TextMessage):
            yield item
