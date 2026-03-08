"""議論エージェント群の構築と実行モジュール

ペルソナ群からAutoGen AssistantAgentを生成し、
RoundRobinGroupChatで議論を実行する。
ストリーミングモードでは1レスずつ非同期に返す。
レートリミットエラー(429)発生時はユーザーに通知して停止する。
キャンセルはAutoGenのCancellationTokenを使い、
ランタイム全体を安全に停止させる。
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


class RateLimitError(Exception):
    """APIレートリミットに達したことを示す例外

    AutoGenのGroupChat内部から呼び出し元へ
    レートリミット情報を伝播させるために使用する。
    """

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


def _is_rate_limit_error(exc: Exception) -> bool:
    """例外がレートリミット関連かどうかを判定する"""
    # openai.RateLimitError (HTTPステータス429)
    exc_type_name = type(exc).__name__
    if exc_type_name == "RateLimitError":
        return True
    # httpxベースのステータスコード確認
    if hasattr(exc, "status_code") and getattr(exc, "status_code", 0) == 429:
        return True
    if hasattr(exc, "response"):
        resp = getattr(exc, "response", None)
        if resp is not None and hasattr(resp, "status_code"):
            if resp.status_code == 429:
                return True
    # メッセージ内の429検出（フォールバック）
    if "429" in str(exc) and ("rate" in str(exc).lower() or "limit" in str(exc).lower()):
        return True
    return False


def _extract_rate_limit_detail(exc: Exception) -> str:
    """レートリミットエラーからユーザー向けの詳細情報を抽出する"""
    msg = str(exc)
    # OpenRouterのmetadataからraw情報を抽出
    if "metadata" in msg and "raw" in msg:
        try:
            import json
            import re
            json_match = re.search(r"\{.*\}", msg, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                raw = data.get("error", {}).get("metadata", {}).get("raw", "")
                if raw:
                    return raw
        except Exception:
            pass
    return msg


class RateLimitedAssistantAgent(BaseChatAgent):
    """レートリミット付きのAssistantAgent

    内部にAssistantAgentを保持し、
    応答前にレートリミッターで待機する。
    APIからレートリミットエラー(429)を受けた場合は
    RateLimitErrorを発生させて呼び出し元に通知する。
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
        try:
            inner_response = await self._inner_agent.on_messages(
                messages, cancellation_token
            )
        except Exception as exc:
            if _is_rate_limit_error(exc):
                detail = _extract_rate_limit_detail(exc)
                raise RateLimitError(
                    f"APIレートリミットに達しました: {detail}",
                    original_error=exc,
                ) from exc
            raise

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
        try:
            response = await self._inner_agent.on_messages(
                messages, cancellation_token
            )
        except Exception as exc:
            if _is_rate_limit_error(exc):
                detail = _extract_rate_limit_detail(exc)
                raise RateLimitError(
                    f"APIレートリミットに達しました: {detail}",
                    original_error=exc,
                ) from exc
            raise

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
    openrouter_url: str = "",
    custom_openai_url: str = "",
    custom_openai_api_key: str = "",
) -> list[RateLimitedAssistantAgent]:
    """ペルソナ群から議論用エージェントを構築する"""
    agents: list[RateLimitedAssistantAgent] = []

    for i, persona in enumerate(personas):
        client = create_model_client(
            provider=provider,
            model_name=model_name,
            settings=settings,
            ollama_url=ollama_url,
            lmstudio_url=lmstudio_url,
            openrouter_url=openrouter_url,
            custom_openai_url=custom_openai_url,
            custom_openai_api_key=custom_openai_api_key,
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
    cancellation_token: CancellationToken | None = None,
) -> TaskResult:
    """RoundRobinGroupChatで議論を実行する（一括完了版）"""
    termination = MaxMessageTermination(max_messages=conversation_count)
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
    cancellation_token: CancellationToken | None = None,
) -> AsyncGenerator[TextMessage | TaskResult, None]:
    """RoundRobinGroupChatで議論を実行する（ストリーミング版）

    メッセージが生成されるたびに1件ずつyieldする。
    最後にTaskResultをyieldする。
    レートリミットエラー発生時はRateLimitErrorをそのまま伝播させる。
    キャンセルはcancellation_tokenで行い、
    run_streamを最後まで安全に消費させる。
    """
    termination = MaxMessageTermination(max_messages=conversation_count)
    team = RoundRobinGroupChat(
        participants=agents,
        termination_condition=termination,
    )

    task_message = f"""スレタイ: {thread_title}

{theme}

議論よろしく"""

    # run_streamは最後まで消費する（途中breakしない）
    # キャンセルはcancellation_tokenを通じてAutoGenに委譲する
    async for item in team.run_stream(
        task=task_message,
        cancellation_token=cancellation_token,
    ):
        if isinstance(item, TaskResult):
            yield item
        elif isinstance(item, TextMessage):
            yield item
