"""議論エージェント群の構築と実行モジュール

ペルソナ群からAutoGen AssistantAgentを生成し、
RoundRobinGroupChat または SelectorGroupChat で議論を実行する。
ストリーミングモードでは1レスずつ非同期に返す。
レートリミットエラー(429)発生時はユーザーに通知して停止する。
ユーザー操作による停止はExternalTerminationを使い、
実行中のHTTP通信を壊さず穏当に終了させる。
各エージェントは累積履歴を自前で保持し、
毎ターンの差分メッセージではなく実際の会話履歴全体を
レス番号付きで再構築してモデルへ渡す。
レス番号スタンプには投稿者IDを含め、
自分自身の投稿へのアンカーを防止する。

chat_pattern の設定により以下のモードを切り替える:
  - "round_robin": RoundRobinGroupChat（固定順の順番発言）
  - "selector": SelectorGroupChat（LLMが文脈に応じて次の発言者を選択）
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
from autogen_agentchat.teams import RoundRobinGroupChat, SelectorGroupChat
from autogen_core import CancellationToken

from src.agents.persona import Persona, build_system_prompt
from src.models.client_factory import create_model_client
from src.utils.rate_limiter import RateLimiter

# SelectorGroupChat 用のセレクタープロンプト（日本語・掲示板風）
SELECTOR_PROMPT = """あなたは匿名掲示板のスレッドの流れを読んで、
次に発言すべき住人を選ぶ進行役です。

【参加者と役割】
{roles}

【これまでの会話】
{history}

上記の会話の流れを読み、{participants} の中から
次に発言させるべき参加者を1人だけ選んでください。

掲示板らしい自然な流れを意識してください:
- 直前のレスに反論・ツッコミできそうな住人を優先する
- 話題が一巡したら新しい切り口を持つ住人に振る
- 同じ住人ばかり続かないようにするが、盛り上がっている時は連続もあり
- スレの序盤はいろんな住人に発言させ、後半は議論を深める

参加者名だけを1つ返してください。それ以外は何も出力しないでください。
"""

# 有効なチャットパターンの定数
CHAT_PATTERN_ROUND_ROBIN = "round_robin"
CHAT_PATTERN_SELECTOR = "selector"
VALID_CHAT_PATTERNS = {CHAT_PATTERN_ROUND_ROBIN, CHAT_PATTERN_SELECTOR}


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


def _extract_display_id_from_source(source: str) -> str:
    """エージェントのsource名からdisplay_idを抽出する

    source名は "agent_{index}_{display_id}" の形式。
    該当しない場合はそのまま返す。
    """
    parts = source.split("_", 2)
    if len(parts) >= 3 and parts[0] == "agent":
        return parts[2]
    return source


def _stamp_res_numbers(
    messages: Sequence[BaseChatMessage],
) -> list[BaseChatMessage]:
    """各メッセージの本文先頭に実際のレス番号と投稿者IDを付与する

    メッセージリスト内のインデックス+1が実際の表示レス番号になる。
    投稿者IDを含めることで、モデルが自分の投稿を識別できるようにする。
    この関数は累積履歴に対して呼び出し、
    レス番号を埋め込んだ新しいリストを返す。
    """
    stamped: list[BaseChatMessage] = []
    for i, msg in enumerate(messages):
        res_number = i + 1
        if isinstance(msg, TextMessage):
            display_id = _extract_display_id_from_source(msg.source)
            prefix = (
                f"[レス番号: >>{res_number} / "
                f"投稿者ID: {display_id}]\n"
            )
            stamped.append(
                TextMessage(
                    content=prefix + msg.content,
                    source=msg.source,
                    models_usage=msg.models_usage,
                )
            )
        else:
            stamped.append(msg)
    return stamped


def normalize_chat_pattern(value: str | None) -> str:
    """チャットパターンを正規化する"""
    if not isinstance(value, str):
        return CHAT_PATTERN_SELECTOR

    normalized = value.strip().lower()
    if normalized in VALID_CHAT_PATTERNS:
        return normalized
    return CHAT_PATTERN_SELECTOR


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
        display_id: str = "",
    ) -> None:
        super().__init__(name=name, description=description)
        self._rate_limiter = rate_limiter
        self._model_client = model_client
        self._max_context_messages = max_context_messages
        self._display_id = display_id
        self._message_history: list[BaseChatMessage] = []
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

    def _remember_messages(
        self,
        messages: Sequence[BaseChatMessage],
    ) -> None:
        """新着メッセージを累積履歴へ追加する"""
        self._message_history.extend(messages)

    def _remember_response(
        self,
        message: BaseChatMessage,
    ) -> None:
        """自分が生成したレスを累積履歴へ追加する"""
        self._message_history.append(message)

    def _trim_messages(
        self,
        messages: Sequence[BaseChatMessage],
    ) -> Sequence[BaseChatMessage]:
        """会話履歴を最新N件に制限する

        最初のメッセージ（スレ立て本文）は常に含め、
        残りは直近の max_context_messages - 1 件を保持する。
        0以下の場合は制限しない。
        """
        if self._max_context_messages <= 0:
            return messages
        if len(messages) <= self._max_context_messages:
            return messages
        if self._max_context_messages == 1:
            return [messages[0]]
        first_msg = messages[0]
        recent = messages[-(self._max_context_messages - 1):]
        return [first_msg] + list(recent)

    def _prepare_messages(
        self,
        messages: Sequence[BaseChatMessage],
    ) -> Sequence[BaseChatMessage]:
        """レス番号の付与→トリミングの順でメッセージを準備する

        先にレス番号を埋め込むことで、トリミングで間引かれても
        残ったメッセージには実際の表示レス番号が保持される。
        """
        stamped = _stamp_res_numbers(messages)
        return self._trim_messages(stamped)

    def _prepare_history_messages(self) -> Sequence[BaseChatMessage]:
        """累積履歴をモデル入力用に整形する"""
        return self._prepare_messages(self._message_history)

    async def _reset_inner_agent(
        self,
        cancellation_token: CancellationToken,
    ) -> None:
        """内部エージェントの状態を毎ターン初期化する"""
        await self._inner_agent.on_reset(cancellation_token)

    async def on_messages(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> Response:
        """メッセージを受け取り、レートリミット後に応答する"""
        self._remember_messages(messages)
        prepared = self._prepare_history_messages()

        await self._rate_limiter.wait()
        await self._reset_inner_agent(cancellation_token)

        try:
            inner_response = await self._inner_agent.on_messages(
                prepared,
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
            rewritten = self._rewrite_text_message(chat_message)
            self._remember_response(rewritten)
            return Response(
                chat_message=rewritten,
                inner_messages=inner_response.inner_messages,
            )

        self._remember_response(chat_message)
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
        self._remember_messages(messages)
        prepared = self._prepare_history_messages()

        await self._rate_limiter.wait()
        await self._reset_inner_agent(cancellation_token)

        last_text_message: TextMessage | None = None
        saw_final_response = False

        try:
            async for item in self._inner_agent.on_messages_stream(
                prepared,
                cancellation_token,
            ):
                if isinstance(item, Response):
                    saw_final_response = True
                    chat_message = item.chat_message
                    if isinstance(chat_message, TextMessage):
                        rewritten = self._rewrite_text_message(chat_message)
                        self._remember_response(rewritten)
                        yield Response(
                            chat_message=rewritten,
                            inner_messages=item.inner_messages,
                        )
                    else:
                        self._remember_response(chat_message)
                        yield item
                elif isinstance(item, TextMessage):
                    rewritten = self._rewrite_text_message(item)
                    last_text_message = rewritten
                    yield rewritten
                else:
                    yield item

            if not saw_final_response and last_text_message is not None:
                self._remember_response(last_text_message)
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
        self._message_history.clear()
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
            display_id=persona.display_id,
        )
        agents.append(agent)

    return agents


def _build_group_chat(
    agents: list[RateLimitedAssistantAgent],
    termination,
    chat_pattern: str = CHAT_PATTERN_SELECTOR,
    selector_model_client: Any = None,
):
    """チャットパターンに応じたグループチャットを構築する"""
    normalized_chat_pattern = normalize_chat_pattern(chat_pattern)

    if (
        normalized_chat_pattern == CHAT_PATTERN_SELECTOR
        and selector_model_client is not None
    ):
        return SelectorGroupChat(
            participants=agents,
            model_client=selector_model_client,
            termination_condition=termination,
            selector_prompt=SELECTOR_PROMPT,
            allow_repeated_speaker=True,
        )

    return RoundRobinGroupChat(
        participants=agents,
        termination_condition=termination,
    )


async def _close_model_client(client: Any) -> None:
    """モデルクライアントを安全に閉じる"""
    close_method = getattr(client, "close", None)
    if not callable(close_method):
        return

    result = close_method()
    if inspect.isawaitable(result):
        await result


async def run_discussion(
    agents: list[RateLimitedAssistantAgent],
    thread_title: str,
    theme: str,
    conversation_count: int,
    external_termination: ExternalTermination | None = None,
    cancellation_token: CancellationToken | None = None,
    chat_pattern: str = CHAT_PATTERN_SELECTOR,
    selector_model_client: Any = None,
) -> TaskResult:
    """グループチャットで議論を実行する（一括完了版）"""
    termination = _build_termination_condition(
        conversation_count,
        external_termination,
    )
    normalized_chat_pattern = normalize_chat_pattern(chat_pattern)

    task_message = f"""スレタイ: {thread_title}

{theme}

議論よろしく"""

    try:
        team = _build_group_chat(
            agents=agents,
            termination=termination,
            chat_pattern=normalized_chat_pattern,
            selector_model_client=selector_model_client,
        )
        result = await team.run(
            task=task_message,
            cancellation_token=cancellation_token,
        )
        return result
    finally:
        if selector_model_client is not None:
            await _close_model_client(selector_model_client)


async def run_discussion_stream(
    agents: list[RateLimitedAssistantAgent],
    thread_title: str,
    theme: str,
    conversation_count: int,
    external_termination: ExternalTermination | None = None,
    cancellation_token: CancellationToken | None = None,
    chat_pattern: str = CHAT_PATTERN_SELECTOR,
    selector_model_client: Any = None,
) -> AsyncGenerator[TextMessage | TaskResult, None]:
    """グループチャットで議論を実行する（ストリーミング版）"""
    termination = _build_termination_condition(
        conversation_count,
        external_termination,
    )
    normalized_chat_pattern = normalize_chat_pattern(chat_pattern)

    task_message = f"""スレタイ: {thread_title}

{theme}

議論よろしく"""

    try:
        team = _build_group_chat(
            agents=agents,
            termination=termination,
            chat_pattern=normalized_chat_pattern,
            selector_model_client=selector_model_client,
        )
        async for item in team.run_stream(
            task=task_message,
            cancellation_token=cancellation_token,
        ):
            if isinstance(item, TaskResult):
                yield item
            elif isinstance(item, TextMessage):
                yield item
    finally:
        if selector_model_client is not None:
            await _close_model_client(selector_model_client)
