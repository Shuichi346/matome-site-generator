"""Web情報取得モジュール

URLからのページ取得とキーワードWeb検索を行い、
テキスト化してLLMのコンテキストに注入するための機能を提供する。
"""

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup


# 共通のHTTPクライアント設定
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}
_TIMEOUT = 15.0


def _clean_text(text: str) -> str:
    """取得したテキストの余分な空白・改行を整理する"""
    # 連続する空行を1つにまとめる
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 行頭末の余分な空白を除去
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def _html_to_text(html_content: str, max_length: int = 5000) -> str:
    """HTMLをプレーンテキストに変換する"""
    soup = BeautifulSoup(html_content, "html.parser")

    # 不要な要素を除去
    for tag in soup.find_all(
        ["script", "style", "nav", "footer", "header", "aside", "iframe"]
    ):
        tag.decompose()

    # メインコンテンツを優先的に取得
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"content|main|entry|post"))
        or soup.find("body")
        or soup
    )

    text = main.get_text(separator="\n", strip=True)
    text = _clean_text(text)

    # 長すぎる場合は切り詰める
    if len(text) > max_length:
        text = text[:max_length] + "\n\n...（以下省略）"

    return text


async def fetch_url(url: str, max_length: int = 5000) -> dict[str, str]:
    """URLからページを取得しテキスト化する

    Args:
        url: 取得対象URL
        max_length: テキストの最大文字数

    Returns:
        {"url": URL, "title": ページタイトル, "content": テキスト内容, "error": エラーメッセージ}
    """
    result: dict[str, str] = {
        "url": url,
        "title": "",
        "content": "",
        "error": "",
    }

    try:
        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            if "text/html" in content_type or "application/xhtml" in content_type:
                html_content = response.text
                soup = BeautifulSoup(html_content, "html.parser")

                # タイトル取得
                title_tag = soup.find("title")
                if title_tag:
                    result["title"] = title_tag.get_text(strip=True)

                result["content"] = _html_to_text(
                    html_content, max_length
                )
            elif "text/plain" in content_type:
                text = response.text
                if len(text) > max_length:
                    text = text[:max_length] + "\n\n...（以下省略）"
                result["content"] = text
                result["title"] = url.split("/")[-1]
            else:
                result["error"] = (
                    f"非対応のContent-Type: {content_type}"
                )

    except httpx.TimeoutException:
        result["error"] = f"タイムアウト: {url}"
    except httpx.HTTPStatusError as e:
        result["error"] = f"HTTPエラー {e.response.status_code}: {url}"
    except Exception as e:
        result["error"] = f"取得失敗: {e}"

    return result


async def fetch_multiple_urls(
    urls: list[str], max_length: int = 5000
) -> list[dict[str, str]]:
    """複数URLを取得する

    Args:
        urls: URLのリスト
        max_length: 各ページのテキスト最大文字数

    Returns:
        取得結果のリスト
    """
    results: list[dict[str, str]] = []
    for url in urls:
        result = await fetch_url(url, max_length)
        results.append(result)
    return results


async def search_web(
    keyword: str, max_results: int = 5, max_length: int = 3000
) -> list[dict[str, str]]:
    """キーワードでWeb検索を行い結果をテキスト化する

    ddgsパッケージ（旧duckduckgo-search）を使用。

    Args:
        keyword: 検索キーワード
        max_results: 取得する検索結果の最大件数
        max_length: 各ページのテキスト最大文字数

    Returns:
        検索結果のリスト。各要素は
        {"url": URL, "title": タイトル, "snippet": 要約, "content": 本文, "error": エラー}
    """
    results: list[dict[str, str]] = []

    try:
        from ddgs import DDGS

        search_results = DDGS().text(keyword, max_results=max_results)

        for sr in search_results:
            entry: dict[str, str] = {
                "url": sr.get("href", ""),
                "title": sr.get("title", ""),
                "snippet": sr.get("body", ""),
                "content": "",
                "error": "",
            }

            # 各ページの本文も取得を試みる
            if entry["url"]:
                try:
                    page = await fetch_url(
                        entry["url"], max_length
                    )
                    if not page["error"]:
                        entry["content"] = page["content"]
                    else:
                        # 本文取得に失敗してもスニペットがある
                        entry["error"] = page["error"]
                except Exception:
                    pass

            results.append(entry)

    except ImportError:
        results.append({
            "url": "",
            "title": "",
            "snippet": "",
            "content": "",
            "error": (
                "ddgs がインストールされていません。"
                "uv sync を実行してください。"
            ),
        })
    except Exception as e:
        results.append({
            "url": "",
            "title": "",
            "snippet": "",
            "content": "",
            "error": f"検索エラー: {e}",
        })

    return results


def format_url_results_as_context(
    results: list[dict[str, str]],
) -> str:
    """URL取得結果をLLMコンテキスト用のテキストに整形する"""
    parts: list[str] = []

    for i, r in enumerate(results, 1):
        if r.get("error"):
            parts.append(
                f"【参考URL {i}】{r['url']}\n"
                f"（取得エラー: {r['error']}）"
            )
            continue

        title = r.get("title", "タイトル不明")
        url = r.get("url", "")
        content = r.get("content", "")

        section = f"【参考URL {i}】{title}\nURL: {url}"
        if content:
            section += f"\n{content}"

        parts.append(section)

    return "\n\n" + "\n\n".join(parts)


def format_search_results_as_context(
    results: list[dict[str, str]],
) -> str:
    """検索結果をLLMコンテキスト用のテキストに整形する"""
    parts: list[str] = []

    for i, r in enumerate(results, 1):
        if r.get("error") and not r.get("snippet"):
            parts.append(f"【検索結果 {i}】（エラー: {r['error']}）")
            continue

        title = r.get("title", "タイトル不明")
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        content = r.get("content", "")

        section = f"【検索結果 {i}】{title}\nURL: {url}"
        if snippet:
            section += f"\n要約: {snippet}"
        if content:
            # コンテンツがスニペットより十分長ければコンテンツを使う
            if len(content) > len(snippet) + 100:
                section += f"\n本文:\n{content}"

        parts.append(section)

    return "\n\n" + "\n\n".join(parts)
