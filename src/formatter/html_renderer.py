"""まとめ風HTML/CSS生成モジュール

まとめエージェントの出力データを
2chまとめサイト風のHTML文字列に変換する。
"""

import html
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

        # ハイライトクラスの決定
        css_class = "res"
        if is_highlighted and highlight_color == "red":
            css_class = "res highlighted-red"
        elif is_highlighted and highlight_color == "blue":
            css_class = "res highlighted-blue"

        # アンカー（>>数字）をリンク風に装飾
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


def _decorate_anchors(text: str) -> str:
    """>>数字 形式のアンカーをスタイル付きspanに変換する"""
    import re
    pattern = r"(&gt;&gt;)(\d+)"
    replacement = r'<span style="color:#ff6600;font-weight:bold;">\1\2</span>'
    return re.sub(pattern, replacement, text)
