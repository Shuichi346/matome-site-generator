"""まとめエージェントの構築と実行モジュール

議論ログを受け取り、2ch/5chまとめサイト風の
構造化データを出力する。
"""

import json
import re
from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import TextMessage

from src.agents.persona import Persona
from src.models.client_factory import create_model_client
from src.utils.rate_limiter import RateLimiter


# まとめエージェントのシステムプロンプト
SUMMARIZER_SYSTEM_PROMPT = """あなたは2ちゃんねる（5ちゃんねる）のまとめサイト管理人です。
以下の掲示板の議論ログを「まとめサイト記事」として編集してください。

【出力フォーマット（JSON）】
必ず以下のJSON形式のみで出力してください。JSON以外のテキストは出力しないでください。

{
  "title": "スレッドタイトル（キャッチーに編集して良い）",
  "category": "カテゴリー名",
  "thread_comments": [
    {
      "number": レス番号(int),
      "name": "投稿者名",
      "id": "投稿者ID",
      "content": "レス本文",
      "is_highlighted": 注目レスかどうか(bool),
      "highlight_color": "red" または "blue" または null
    }
  ],
  "editor_comment": "管理人のコメント（記事冒頭に表示される短いリード文）",
  "reactions_summary": "読者の反応まとめ（記事末尾用テキスト）"
}

【編集ルール】
- 全レスを含める必要はない。面白いレス、重要なレスを選んでピックアップする
- 特に面白いレスや核心をつくレスには is_highlighted: true を付ける
- ハイライト色は重要な意見に "red"、面白い意見に "blue" を付ける
- レスの順序は元の議論順を基本とするが、読みやすいように並べ替えても良い
- スレッドタイトルは元のテーマを活かしつつ、まとめサイト風にキャッチーに編集する
- 管理人コメントは短くまとめる
- 出力はJSON形式のみ。前後に余計なテキストを入れない
"""


def _format_discussion_log(
    result: TaskResult,
    personas: list[Persona],
) -> str:
    """議論結果をまとめエージェントに渡すログ文字列に変換する"""
    agent_persona_map: dict[str, Persona] = {}
    for i, persona in enumerate(personas):
        agent_persona_map[f"agent_{i}_{persona.display_id}"] = persona

    lines: list[str] = []
    res_number = 1

    for msg in result.messages:
        if not isinstance(msg, TextMessage):
            continue
        source = msg.source
        if source == "user":
            lines.append(f"{res_number} 名前: スレ主 ID:Thread0P\n{msg.content}")
            res_number += 1
            continue

        persona = agent_persona_map.get(source)
        if persona:
            name = persona.name
            display_id = persona.display_id
        else:
            name = "名無しさん"
            display_id = source[-8:] if len(source) >= 8 else source

        lines.append(f"{res_number} 名前: {name} ID:{display_id}\n{msg.content}")
        res_number += 1

    return "\n\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    """テキストからJSON部分を抽出してパースする"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1))
        except json.JSONDecodeError:
            pass

    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError("まとめJSONの抽出に失敗しました")


async def generate_thread_title(
    theme: str,
    provider: str,
    model_name: str,
    rate_limiter: RateLimiter,
    settings: dict[str, Any] | None = None,
    ollama_url: str = "http://localhost:11434",
    lmstudio_url: str = "http://localhost:1234/v1",
    openrouter_url: str = "",
    custom_openai_url: str = "",
    custom_openai_api_key: str = "",
) -> str:
    """AIにスレッドタイトルを自動生成させる"""
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

    agent = AssistantAgent(
        name="title_generator",
        model_client=client,
        system_message=(
            "あなたは2ちゃんねるのスレッドタイトル生成の達人です。\n"
            "与えられたテーマから、2ch/5ch風のスレッドタイトルを1つだけ生成してください。\n"
            "タイトルのみを出力し、他の文章は含めないでください。\n"
            "【や】で始めたり、【悲報】【朗報】【速報】などのタグを付けても良い。\n"
            "例:\n"
            "【悲報】推しの子の最終回、ガチで賛否両論ｗｗｗｗ\n"
            "ワイ「ChatGPT使ってみるか…」→結果ｗｗｗ\n"
        ),
    )

    await rate_limiter.wait()
    result = await agent.run(task=f"テーマ: {theme}")

    for msg in reversed(result.messages):
        if isinstance(msg, TextMessage) and msg.source != "user":
            title = msg.content.strip().strip('"').strip("'")
            await client.close()
            return title

    await client.close()
    return f"【議論】{theme}"


async def run_summarizer(
    discussion_result: TaskResult,
    personas: list[Persona],
    provider: str,
    model_name: str,
    rate_limiter: RateLimiter,
    settings: dict[str, Any] | None = None,
    ollama_url: str = "http://localhost:11434",
    lmstudio_url: str = "http://localhost:1234/v1",
    openrouter_url: str = "",
    custom_openai_url: str = "",
    custom_openai_api_key: str = "",
) -> dict[str, Any]:
    """まとめエージェントを実行して構造化データを返す"""
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

    agent = AssistantAgent(
        name="summarizer",
        model_client=client,
        system_message=SUMMARIZER_SYSTEM_PROMPT,
    )

    log_text = _format_discussion_log(discussion_result, personas)

    await rate_limiter.wait()
    task_content = f"以下の議論ログをまとめてください:\n\n{log_text}"
    result = await agent.run(task=task_content)

    for msg in reversed(result.messages):
        if isinstance(msg, TextMessage) and msg.source != "user":
            try:
                matome_data = _extract_json(msg.content)
                await client.close()
                return matome_data
            except ValueError:
                continue

    await client.close()

    return {
        "title": "まとめ",
        "category": "議論",
        "thread_comments": [
            {
                "number": i + 1,
                "name": "名無しさん",
                "id": "unknown",
                "content": msg.content if isinstance(msg, TextMessage) else str(msg),
                "is_highlighted": False,
                "highlight_color": None,
            }
            for i, msg in enumerate(discussion_result.messages)
            if isinstance(msg, TextMessage) and msg.source != "user"
        ],
        "editor_comment": "まとめの自動生成に一部失敗しました。",
        "reactions_summary": "",
    }
