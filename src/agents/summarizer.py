"""まとめエージェントの構築と実行モジュール"""

import inspect
import json
import re
from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage

from src.models.client_factory import create_model_client
from src.utils.rate_limiter import RateLimiter


SUMMARIZER_SYSTEM_PROMPT = """あなたは2ちゃんねる（5ちゃんねる）のまとめサイト編集者です。
入力されるのは、実際に画面表示した投稿一覧です。
本文や名前やIDを書き換えずに、採用するレス番号と記事メタ情報だけを決めてください。

【出力ルール】
- 必ずJSONのみを返す
- `picked_comments` には採用するレス番号だけを入れる
- `number` は入力に存在するレス番号だけを選ぶ
- `is_highlighted` は強調したいレスだけ true にする
- `highlight_color` は "red" / "blue" / null のいずれか
- `editor_comment` は短い導入文
- `reactions_summary` は記事末尾向けの短い総括

【出力JSON】
{
  "title": "まとめ記事タイトル",
  "category": "カテゴリー名",
  "picked_comments": [
    {
      "number": 3,
      "is_highlighted": true,
      "highlight_color": "red"
    }
  ],
  "editor_comment": "管理人コメント",
  "reactions_summary": "読者の反応まとめ"
}
"""


def _format_thread_posts_for_summary(
    thread_posts: list[dict[str, Any]],
) -> str:
    """表示済み投稿を要約用の文字列に変換する"""
    lines: list[str] = []
    for post in thread_posts:
        number = int(post.get("number", 0))
        name = str(post.get("name", "名無しさん"))
        display_id = str(post.get("display_id", ""))
        content = str(post.get("content", ""))
        lines.append(
            f"{number} 名前: {name} ID:{display_id}\n{content}"
        )
    return "\n\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    """テキストからJSON部分を抽出してパースする"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    code_block_match = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        text,
        re.DOTALL,
    )
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


def _stringify_field(value: Any, default: str) -> str:
    """要約結果の文字列フィールドを正規化する"""
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _to_int(value: Any) -> int | None:
    """整数化を試みる"""
    try:
        if isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    """bool値へ寄せる"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def _normalize_highlight_color(value: Any) -> str | None:
    """強調色を正規化する"""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"red", "blue"}:
        return text
    return None


def _build_fallback_summary(
    thread_posts: list[dict[str, Any]],
    default_title: str,
    category: str,
    reactions_summary: str,
) -> dict[str, Any]:
    """安全なフォールバック結果を返す"""
    return {
        "title": default_title or "まとめ",
        "category": category or "議論",
        "thread_comments": [
            {
                "number": int(post.get("number", 0)),
                "name": str(post.get("name", "名無しさん")),
                "id": str(post.get("display_id", "")),
                "content": str(post.get("content", "")),
                "is_highlighted": False,
                "highlight_color": None,
            }
            for post in thread_posts
        ],
        "editor_comment": "まとめの自動生成に一部失敗しました。",
        "reactions_summary": reactions_summary,
    }


def _extract_candidate_comments(raw_data: dict[str, Any]) -> list[Any]:
    """新旧スキーマから採用候補のリストを取り出す"""
    picked_comments = raw_data.get("picked_comments")
    if isinstance(picked_comments, list):
        return picked_comments

    legacy_comments = raw_data.get("thread_comments")
    if isinstance(legacy_comments, list):
        return legacy_comments

    return []


def _normalize_summary_result(
    raw_data: Any,
    thread_posts: list[dict[str, Any]],
    default_title: str,
) -> dict[str, Any]:
    """要約JSONを検証・正規化して互換形式へ変換する"""
    if not isinstance(raw_data, dict):
        return _build_fallback_summary(
            thread_posts=thread_posts,
            default_title=default_title or "まとめ",
            category="議論",
            reactions_summary="",
        )

    title = _stringify_field(
        raw_data.get("title"),
        default_title or "まとめ",
    )
    category = _stringify_field(raw_data.get("category"), "議論")
    editor_comment = _stringify_field(
        raw_data.get("editor_comment"),
        "",
    )
    reactions_summary = _stringify_field(
        raw_data.get("reactions_summary"),
        "",
    )

    posts_by_number: dict[int, dict[str, Any]] = {}
    for post in thread_posts:
        number = _to_int(post.get("number"))
        if number is not None:
            posts_by_number[number] = post

    picked_comments: list[dict[str, Any]] = []
    seen_numbers: set[int] = set()
    for item in _extract_candidate_comments(raw_data):
        if not isinstance(item, dict):
            continue

        number = _to_int(item.get("number"))
        if number is None or number not in posts_by_number:
            continue
        if number in seen_numbers:
            continue

        picked_comments.append({
            "number": number,
            "is_highlighted": _to_bool(
                item.get("is_highlighted", False)
            ),
            "highlight_color": _normalize_highlight_color(
                item.get("highlight_color")
            ),
        })
        seen_numbers.add(number)

    if not picked_comments:
        return _build_fallback_summary(
            thread_posts=thread_posts,
            default_title=title,
            category=category,
            reactions_summary=reactions_summary,
        )

    thread_comments: list[dict[str, Any]] = []
    for picked in picked_comments:
        original_post = posts_by_number[picked["number"]]
        thread_comments.append({
            "number": picked["number"],
            "name": str(original_post.get("name", "名無しさん")),
            "id": str(original_post.get("display_id", "")),
            "content": str(original_post.get("content", "")),
            "is_highlighted": picked["is_highlighted"],
            "highlight_color": picked["highlight_color"],
        })

    return {
        "title": title,
        "category": category,
        "thread_comments": thread_comments,
        "editor_comment": editor_comment,
        "reactions_summary": reactions_summary,
    }


async def _close_model_client(client: Any) -> None:
    """モデルクライアントを安全に閉じる"""
    close_method = getattr(client, "close", None)
    if not callable(close_method):
        return

    result = close_method()
    if inspect.isawaitable(result):
        await result


async def generate_thread_title(
    theme: str,
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
    """AIにスレッドタイトルを自動生成させる"""
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
                return msg.content.strip().strip('"').strip("'")

        return f"【議論】{theme}"
    finally:
        await _close_model_client(client)


async def run_summarizer(
    thread_posts: list[dict[str, Any]],
    thread_title: str,
    provider: str,
    model_name: str,
    rate_limiter: RateLimiter,
    settings: dict[str, Any] | None = None,
    ollama_url: str = "http://localhost:11434",
    openrouter_url: str = "",
    custom_openai_url: str = "",
    custom_openai_api_key: str = "",
    ollama_think: bool | None = None,
) -> dict[str, Any]:
    """まとめエージェントを実行して構造化データを返す"""
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
            name="summarizer",
            model_client=client,
            system_message=SUMMARIZER_SYSTEM_PROMPT,
        )

        log_text = _format_thread_posts_for_summary(thread_posts)

        await rate_limiter.wait()
        task_content = (
            f"スレッドタイトル: {thread_title}\n\n"
            "以下の表示済み投稿一覧から、採用するレス番号だけを選んでください。\n\n"
            f"{log_text}"
        )
        result = await agent.run(task=task_content)

        raw_data: Any = None
        for msg in reversed(result.messages):
            if isinstance(msg, TextMessage) and msg.source != "user":
                try:
                    raw_data = _extract_json(msg.content)
                    break
                except ValueError:
                    raw_data = None

        return _normalize_summary_result(
            raw_data=raw_data,
            thread_posts=thread_posts,
            default_title=thread_title,
        )
    finally:
        await _close_model_client(client)
