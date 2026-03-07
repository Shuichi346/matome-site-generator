"""まとめ風HTML/CSS生成モジュール

まとめエージェントの出力データを2chまとめサイト風のHTML文字列に変換する。
また、リアルタイムスレッド表示用のHTMLも生成する。
"""

import html
import re
from pathlib import Path
from typing import Any


def _load_css() -> str:
    """CSSファイルを読み込む。ファイルがなければデフォルトCSSを返す"""
    css_path = Path(__file__).resolve().parent.parent / "templates" / "matome.css"
    if css_path.exists():
        return css_path.read_text(encoding="utf-8")
    return _default_css()


def _default_css() -> str:
    """デフォルトのまとめ風CSS"""
    return """
.matome-container {
    font-family: 'Hiragino Kaku Gothic ProN', 'メイリオ', sans-serif;
    max-width: 800px;
    margin: 0 auto;
    background-color: #f5f0e8;
    border: 1px solid #d3c5a0;
    border-radius: 4px;
    padding: 0;
}
.matome-header {
    background-color: #8b0000;
    color: #ffffff;
    padding: 16px 20px;
    border-radius: 4px 4px 0 0;
}
.matome-header .thread-title {
    font-size: 1.3em;
    margin: 0 0 8px 0;
    line-height: 1.4;
}
.matome-header .category-label {
    font-size: 0.85em;
    color: #ffcccc;
    margin: 0 0 8px 0;
}
.matome-header .editor-comment {
    font-size: 0.95em;
    color: #ffe0e0;
    margin: 0;
    line-height: 1.5;
}
.thread-body {
    padding: 12px 20px;
}
.res {
    background-color: #efefef;
    border: 1px solid #d0d0d0;
    border-radius: 3px;
    margin-bottom: 10px;
    padding: 10px 14px;
}
.res.highlighted-red {
    border-left: 4px solid #ff4444;
    background-color: #fff5f5;
}
.res.highlighted-blue {
    border-left: 4px solid #4444ff;
    background-color: #f5f5ff;
}
.res-header {
    font-size: 0.85em;
    margin-bottom: 6px;
    color: #666666;
}
.res-number {
    font-weight: bold;
    color: #333333;
    margin-right: 8px;
}
.res-name {
    color: #117743;
    font-weight: bold;
    margin-right: 8px;
}
.res-id {
    color: #999999;
}
.res-content {
    font-size: 0.95em;
    line-height: 1.6;
    color: #333333;
    white-space: pre-wrap;
    word-wrap: break-word;
}
.matome-footer {
    background-color: #e8e0d0;
    padding: 14px 20px;
    border-radius: 0 0 4px 4px;
    border-top: 1px solid #d3c5a0;
}
.reactions-summary {
    font-size: 0.9em;
    color: #555555;
    line-height: 1.5;
    margin: 0;
}
"""


# スレッド表示専用のCSS
THREAD_CSS = """
.thread-container {
    font-family: 'IPAMonaPGothic', 'Mona', 'MS PGothic', sans-serif;
    max-width: 800px;
    margin: 0 auto;
    background-color: #efefef;
    border: 1px solid #aaaaaa;
}
.thread-header {
    background-color: #800000;
    color: #ffffff;
    padding: 8px 12px;
    font-size: 1.1em;
    font-weight: bold;
}
.thread-header small {
    font-weight: normal;
    font-size: 0.8em;
    color: #ffcccc;
}
.thread-posts {
    padding: 4px 8px;
}
.thread-post {
    padding: 4px 0;
    border-bottom: 1px solid #d0d0d0;
}
.thread-post:last-child {
    border-bottom: none;
}
.thread-post-header {
    font-size: 0.85em;
    line-height: 1.4;
}
.thread-post-number {
    color: #000000;
    font-weight: bold;
}
.thread-post-name {
    color: #117743;
    font-weight: bold;
}
.thread-post-date {
    color: #666666;
}
.thread-post-id {
    color: #bb0000;
}
.thread-post-content {
    font-size: 0.95em;
    line-height: 1.5;
    color: #000000;
    padding: 2px 0 6px 20px;
    white-space: pre-wrap;
    word-wrap: break-word;
}
.thread-post-content .anchor {
    color: #ff6600;
    font-weight: bold;
}
.thread-post.new-post {
    animation: highlight-new 1.5s ease-out;
}
@keyframes highlight-new {
    0%   { background-color: #ffffaa; }
    100% { background-color: transparent; }
}
.thread-loading {
    text-align: center;
    padding: 12px;
    color: #666666;
    font-size: 0.9em;
}
.thread-loading .spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid #cccccc;
    border-top-color: #800000;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    vertical-align: middle;
    margin-right: 6px;
}
@keyframes spin {
    to { transform: rotate(360deg); }
}
"""


def _decorate_anchors(text: str) -> str:
    """>>数字 形式のアンカーをスタイル付きspanに変換する"""
    pattern = r"(&gt;&gt;)(\d+)"
    replacement = r'<span class="anchor">\1\2</span>'
    return re.sub(pattern, replacement, text)


def render_matome_html(matome_data: dict[str, Any]) -> str:
    """まとめデータをHTML文字列に変換する

    Args:
        matome_data: まとめエージェントの出力辞書

    Returns:
        完全なHTMLフラグメント文字列（CSS込み）
    """
    css = _load_css()
    title = html.escape(str(matome_data.get("title", "まとめ")))
    category = html.escape(str(matome_data.get("category", "")))
    editor_comment = html.escape(str(matome_data.get("editor_comment", "")))
    reactions = html.escape(str(matome_data.get("reactions_summary", "")))

    comments_html = ""
    for comment in matome_data.get("thread_comments", []):
        number = int(comment.get("number", 0))
        name = html.escape(str(comment.get("name", "名無しさん")))
        cid = html.escape(str(comment.get("id", "")))
        content = html.escape(str(comment.get("content", "")))
        is_highlighted = comment.get("is_highlighted", False)
        highlight_color = comment.get("highlight_color")

        css_class = "res"
        if is_highlighted and highlight_color == "red":
            css_class = "res highlighted-red"
        elif is_highlighted and highlight_color == "blue":
            css_class = "res highlighted-blue"

        content = _decorate_anchors(content)

        comments_html += f"""
    <div class="{css_class}">
      <div class="res-header">
        <span class="res-number">{number}</span>
        <span class="res-name">{name}</span>
        <span class="res-id">ID:{cid}</span>
      </div>
      <div class="res-content">{content}</div>
    </div>"""

    html_output = f"""<style>{css}</style>
<div class="matome-container">
  <div class="matome-header">
    <h1 class="thread-title">{title}</h1>
    <p class="category-label">{category}</p>
    <p class="editor-comment">{editor_comment}</p>
  </div>
  <div class="thread-body">
    {comments_html}
  </div>
  <div class="matome-footer">
    <p class="reactions-summary">{reactions}</p>
  </div>
</div>"""

    return html_output


# ===== スレッド風リアルタイム表示 =====

def render_thread_header(title: str) -> str:
    """スレッドのヘッダー部分のHTMLを生成する

    Args:
        title: スレッドタイトル

    Returns:
        HTMLフラグメント文字列
    """
    escaped_title = html.escape(title)
    return f"""<style>{THREAD_CSS}</style>
<div class="thread-container">
  <div class="thread-header">
    {escaped_title}
    <br><small>このスレッドはAIが自動生成しています</small>
  </div>
  <div class="thread-posts">
"""


def render_thread_post(
    number: int,
    name: str,
    display_id: str,
    date_str: str,
    content: str,
    is_new: bool = False,
) -> str:
    """スレッドの1レス分のHTMLを生成する

    Args:
        number: レス番号
        name: 表示名
        display_id: ID文字列
        date_str: 日時文字列
        content: レス本文
        is_new: 新着レスかどうか（アニメーション用）

    Returns:
        HTMLフラグメント文字列
    """
    escaped_name = html.escape(name)
    escaped_id = html.escape(display_id)
    escaped_date = html.escape(date_str)
    escaped_content = html.escape(content)
    escaped_content = _decorate_anchors(escaped_content)

    new_class = " new-post" if is_new else ""

    return f"""
    <div class="thread-post{new_class}">
      <div class="thread-post-header">
        <span class="thread-post-number">{number}</span> ：
        <span class="thread-post-name">{escaped_name}</span>
        ：<span class="thread-post-date">{escaped_date}</span>
        <span class="thread-post-id">ID:{escaped_id}</span>
      </div>
      <div class="thread-post-content">{escaped_content}</div>
    </div>"""


def render_thread_loading(current: int, total: int) -> str:
    """読み込み中のインジケーターHTMLを生成する

    Args:
        current: 現在のレス数
        total: 目標レス数

    Returns:
        HTMLフラグメント文字列
    """
    return f"""
    <div class="thread-loading">
      <span class="spinner"></span>
      レスを書き込み中... ({current}/{total})
    </div>"""


def render_thread_footer(total: int) -> str:
    """スレッドのフッター部分のHTMLを生成する

    Args:
        total: 総レス数

    Returns:
        HTMLフラグメント文字列
    """
    return f"""
  </div>
  <div class="thread-header" style="font-size:0.85em; font-weight:normal;">
    このスレッドは{total}レスで終了しました。
  </div>
</div>"""
