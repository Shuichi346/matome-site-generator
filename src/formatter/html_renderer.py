"""まとめ風HTML/CSS生成モジュール

まとめエージェントの出力データを2chまとめサイト風のHTML文字列に変換する。
また、リアルタイムスレッド表示用のHTMLも生成する。
Gradioのgr.HTMLコンポーネントでは<style>タグが無視される場合があるため、
Gradio向け表示はインラインスタイルで記述する。
スタンドアロンHTML出力では<style>タグを使用する。
"""

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _decorate_anchors(text: str) -> str:
    """>>数字 形式のアンカーをインラインスタイル付きspanに変換する"""
    pattern = r"(&gt;&gt;)(\d+)"
    replacement = (
        r'<span style="color:#ff6600;font-weight:bold;cursor:pointer;">'
        r"\1\2</span>"
    )
    return re.sub(pattern, replacement, text)


def _decorate_anchors_thread(text: str) -> str:
    """スレッド表示用のアンカー装飾"""
    pattern = r"(&gt;&gt;)(\d+)"
    replacement = (
        r'<span style="color:#ff6600;font-weight:bold;">\1\2</span>'
    )
    return re.sub(pattern, replacement, text)


def _decorate_anchors_css(text: str) -> str:
    """CSSクラスベースのアンカー装飾（スタンドアロンHTML用）"""
    pattern = r"(&gt;&gt;)(\d+)"
    replacement = r'<span class="anchor">\1\2</span>'
    return re.sub(pattern, replacement, text)


# 共通フォント指定
_FONT = "'Hiragino Kaku Gothic ProN','メイリオ',Meiryo,sans-serif"


# ========================================
# まとめサイト風 HTML（Gradioインラインスタイル版）
# ========================================

def render_matome_html(matome_data: dict[str, Any]) -> str:
    """まとめデータをHTML文字列に変換する（Gradio表示用・インラインスタイル）"""
    title = html.escape(str(matome_data.get("title", "まとめ")))
    category = html.escape(str(matome_data.get("category", "")))
    editor_comment = html.escape(
        str(matome_data.get("editor_comment", ""))
    )
    reactions = html.escape(
        str(matome_data.get("reactions_summary", ""))
    )
    now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    comments_count = len(matome_data.get("thread_comments", []))

    comments_html = ""
    for idx, comment in enumerate(matome_data.get("thread_comments", [])):
        number = int(comment.get("number", 0))
        name = html.escape(str(comment.get("name", "名無しさん")))
        cid = html.escape(str(comment.get("id", "")))
        content = html.escape(str(comment.get("content", "")))
        is_highlighted = comment.get("is_highlighted", False)
        highlight_color = comment.get("highlight_color")

        res_style = "padding:0 20px;"
        if idx > 0:
            res_style += "border-top:1px solid #f0f0f0;"
        if is_highlighted and highlight_color == "red":
            res_style += (
                "background:#fff5f5;"
                "border-left:4px solid #e74c3c;"
                "padding-left:16px;"
            )
        elif is_highlighted and highlight_color == "blue":
            res_style += (
                "background:#f0f4ff;"
                "border-left:4px solid #3498db;"
                "padding-left:16px;"
            )

        content = _decorate_anchors(content)
        fake_date = datetime.now().strftime("%y/%m/%d")
        fake_time = datetime.now().strftime("%H:%M:%S")
        timestamp_str = f"{fake_date}(土) {fake_time}"

        header_style = (
            "font-size:0.82em;line-height:1.6;"
            "padding-top:14px;color:#333;"
        )
        num_style = "font-weight:bold;color:#333;"
        name_style = "color:#117743;font-weight:bold;"
        ts_style = "color:#999;margin-left:2px;"
        content_style = (
            "font-size:0.95em;line-height:1.7;color:#333;"
            "padding:10px 0 16px 0;margin:0;"
            "white-space:pre-wrap;word-wrap:break-word;"
        )

        comments_html += f"""
    <div style="{res_style}">
      <div style="{header_style}">
        <span style="{num_style}">{number}:</span>
        <span style="{name_style}">{name}</span>
        <span style="{ts_style}">{timestamp_str} ID:{cid}</span>
      </div>
      <div style="{content_style}">{content}</div>
    </div>"""

    editor_html = ""
    if editor_comment:
        editor_html = (
            f'\n  <div style="padding:14px 20px;font-size:0.92em;'
            f"color:#333;line-height:1.7;"
            f'border-bottom:1px solid #eee;background:#fff;">'
            f"{editor_comment}</div>"
        )

    footer_html = ""
    if reactions:
        footer_html = (
            f'\n  <div style="padding:14px 20px;background:#f8f8f8;'
            f"border-top:1px solid #e0e0e0;font-size:0.85em;"
            f'color:#666;line-height:1.6;">'
            f"{reactions}</div>"
        )

    wrap_style = (
        f"font-family:{_FONT};"
        "max-width:780px;margin:0 auto;background:#fff;"
        "border:1px solid #dcdcdc;border-radius:4px;overflow:hidden;"
    )
    title_bar_style = (
        "background:#fff;padding:14px 20px 12px;"
        "border-bottom:3px solid #ff6600;"
    )
    title_text_style = (
        "margin:0;padding:0;font-size:1.3em;"
        "font-weight:bold;line-height:1.45;color:#333;"
    )
    meta_style = (
        "display:flex;justify-content:space-between;"
        "align-items:center;padding:6px 20px;"
        "font-size:0.78em;color:#999;"
        "border-bottom:1px solid #eee;background:#fafafa;"
    )
    meta_right_style = "display:flex;gap:12px;"
    cat_style = "color:#ff6600;font-weight:bold;"
    count_style = "color:#ff6600;font-weight:bold;"
    source_style = (
        "padding:10px 20px;font-size:0.75em;color:#aaa;"
        "border-top:1px solid #f0f0f0;background:#fafafa;"
    )

    return f"""<div style="{wrap_style}">
  <div style="{title_bar_style}">
    <h2 style="{title_text_style}">{title}</h2>
  </div>
  <div style="{meta_style}">
    <span>{now_str}</span>
    <span style="{meta_right_style}">
      <span style="{cat_style}">カテゴリ：{category}</span>
      <span style="{count_style}">コメント({comments_count})</span>
    </span>
  </div>{editor_html}
  <div style="padding:0;background:#fff;">{comments_html}
  </div>{footer_html}
  <div style="{source_style}">
    このまとめはAIが自動生成しました
  </div>
</div>"""


# ========================================
# スレッド風リアルタイム表示 HTML（Gradioインラインスタイル版）
# ========================================

def render_thread_header(title: str) -> str:
    """スレッドのヘッダー部分のHTMLを生成する"""
    escaped_title = html.escape(title)

    animation_css = """<style>
@keyframes spin-thread {
    to { transform: rotate(360deg); }
}
@keyframes highlight-new-thread {
    0%   { background-color: #ffffaa; }
    100% { background-color: transparent; }
}
</style>"""

    container_style = (
        "font-family:'IPAMonaPGothic','Mona','MS PGothic',sans-serif;"
        "max-width:800px;margin:0 auto;"
        "background-color:#efefef;border:1px solid #aaa;"
    )
    header_style = (
        "background-color:#800000;color:#fff;"
        "padding:8px 12px;font-size:1.1em;font-weight:bold;"
    )
    small_style = (
        "font-weight:normal;font-size:0.8em;color:#ffcccc;"
    )

    return f"""{animation_css}
<div style="{container_style}">
  <div style="{header_style}">
    {escaped_title}
    <br><small style="{small_style}">このスレッドはAIが自動生成しています</small>
  </div>
  <div style="padding:4px 8px;">
"""


def render_thread_post(
    number: int,
    name: str,
    display_id: str,
    date_str: str,
    content: str,
    is_new: bool = False,
) -> str:
    """スレッドの1レス分のHTMLを生成する"""
    escaped_name = html.escape(name)
    escaped_id = html.escape(display_id)
    escaped_date = html.escape(date_str)
    escaped_content = html.escape(content)
    escaped_content = _decorate_anchors_thread(escaped_content)

    post_style = "padding:4px 0;border-bottom:1px solid #d0d0d0;"
    if is_new:
        post_style += "animation:highlight-new-thread 1.5s ease-out;"

    header_style = "font-size:0.85em;line-height:1.4;"
    num_style = "color:#000;font-weight:bold;"
    name_style = "color:#117743;font-weight:bold;"
    date_style = "color:#666;"
    id_style = "color:#bb0000;"
    content_style = (
        "font-size:0.95em;line-height:1.5;color:#000;"
        "padding:2px 0 6px 20px;"
        "white-space:pre-wrap;word-wrap:break-word;"
    )

    return f"""
    <div style="{post_style}">
      <div style="{header_style}">
        <span style="{num_style}">{number}</span> ：
        <span style="{name_style}">{escaped_name}</span>
        ：<span style="{date_style}">{escaped_date}</span>
        <span style="{id_style}">ID:{escaped_id}</span>
      </div>
      <div style="{content_style}">{escaped_content}</div>
    </div>"""


def render_thread_loading(current: int, total: int) -> str:
    """読み込み中のインジケーターHTMLを生成する"""
    loading_style = (
        "text-align:center;padding:12px;color:#666;font-size:0.9em;"
    )
    spinner_style = (
        "display:inline-block;width:16px;height:16px;"
        "border:2px solid #ccc;border-top-color:#800000;"
        "border-radius:50%;animation:spin-thread 0.8s linear infinite;"
        "vertical-align:middle;margin-right:6px;"
    )

    return f"""
    <div style="{loading_style}">
      <span style="{spinner_style}"></span>
      レスを書き込み中... ({current}/{total})
    </div>"""


def render_thread_footer(total: int) -> str:
    """スレッドのフッター部分のHTMLを生成する"""
    footer_style = (
        "background-color:#800000;color:#fff;"
        "padding:8px 12px;font-size:0.85em;font-weight:normal;"
    )
    return f"""
  </div>
  <div style="{footer_style}">
    このスレッドは{total}レスで終了しました。
  </div>
</div>"""


# ========================================
# スタンドアロンHTML出力（ファイルダウンロード用）
# CSSクラス + <style>タグで完結する単一HTML
# ========================================

_STANDALONE_BASE_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Hiragino Kaku Gothic ProN', 'メイリオ', Meiryo, sans-serif;
    background: #f5f5f5;
    padding: 20px;
}
.anchor { color: #ff6600; font-weight: bold; cursor: pointer; }
"""

_STANDALONE_MATOME_CSS = """
.matome-wrap {
    max-width: 780px; margin: 0 auto; background: #fff;
    border: 1px solid #dcdcdc; border-radius: 4px; overflow: hidden;
}
.matome-title-bar {
    background: #fff; padding: 14px 20px 12px;
    border-bottom: 3px solid #ff6600;
}
.matome-title-bar h2 {
    margin: 0; padding: 0; font-size: 1.3em;
    font-weight: bold; line-height: 1.45; color: #333;
}
.matome-meta {
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 20px; font-size: 0.78em; color: #999;
    border-bottom: 1px solid #eee; background: #fafafa;
}
.matome-meta .meta-right { display: flex; gap: 12px; }
.meta-category, .meta-comments { color: #ff6600; font-weight: bold; }
.matome-editor-comment {
    padding: 14px 20px; font-size: 0.92em; color: #333;
    line-height: 1.7; border-bottom: 1px solid #eee;
}
.matome-body { padding: 0; }
.matome-res { padding: 0 20px; }
.matome-res + .matome-res { border-top: 1px solid #f0f0f0; }
.matome-res.hl-red {
    background: #fff5f5; border-left: 4px solid #e74c3c; padding-left: 16px;
}
.matome-res.hl-blue {
    background: #f0f4ff; border-left: 4px solid #3498db; padding-left: 16px;
}
.matome-res-header {
    font-size: 0.82em; line-height: 1.6; padding-top: 14px; color: #333;
}
.matome-res-num { font-weight: bold; color: #333; }
.matome-res-name { color: #117743; font-weight: bold; }
.matome-res-timestamp { color: #999; margin-left: 2px; }
.matome-res-content {
    font-size: 0.95em; line-height: 1.7; color: #333;
    padding: 10px 0 16px 0; white-space: pre-wrap; word-wrap: break-word;
}
.matome-footer {
    padding: 14px 20px; background: #f8f8f8;
    border-top: 1px solid #e0e0e0; font-size: 0.85em;
    color: #666; line-height: 1.6;
}
.matome-source {
    padding: 10px 20px; font-size: 0.75em; color: #aaa;
    border-top: 1px solid #f0f0f0; background: #fafafa;
}
"""

_STANDALONE_THREAD_CSS = """
.thread-container {
    font-family: 'IPAMonaPGothic', 'Mona', 'MS PGothic', sans-serif;
    max-width: 800px; margin: 0 auto;
    background-color: #efefef; border: 1px solid #aaa;
}
.thread-header {
    background-color: #800000; color: #fff;
    padding: 8px 12px; font-size: 1.1em; font-weight: bold;
}
.thread-header small {
    font-weight: normal; font-size: 0.8em; color: #ffcccc;
}
.thread-posts { padding: 4px 8px; }
.thread-post { padding: 4px 0; border-bottom: 1px solid #d0d0d0; }
.thread-post:last-child { border-bottom: none; }
.thread-post-header { font-size: 0.85em; line-height: 1.4; }
.thread-post-number { color: #000; font-weight: bold; }
.thread-post-name { color: #117743; font-weight: bold; }
.thread-post-date { color: #666; }
.thread-post-id { color: #bb0000; }
.thread-post-content {
    font-size: 0.95em; line-height: 1.5; color: #000;
    padding: 2px 0 6px 20px; white-space: pre-wrap; word-wrap: break-word;
}
.thread-footer {
    background-color: #800000; color: #fff;
    padding: 8px 12px; font-size: 0.85em; font-weight: normal;
}
"""

_STANDALONE_RAWLOG_CSS = """
.rawlog-container {
    max-width: 800px; margin: 0 auto; background: #fff;
    border: 1px solid #dcdcdc; border-radius: 4px; overflow: hidden;
}
.rawlog-header {
    background: #333; color: #fff; padding: 10px 16px;
    font-size: 1.1em; font-weight: bold;
}
.rawlog-body { padding: 16px; }
.rawlog-entry {
    padding: 8px 0; border-bottom: 1px solid #f0f0f0;
}
.rawlog-entry:last-child { border-bottom: none; }
.rawlog-source {
    font-size: 0.8em; color: #666; font-weight: bold; margin-bottom: 2px;
}
.rawlog-content {
    font-size: 0.9em; line-height: 1.5; color: #333;
    white-space: pre-wrap; word-wrap: break-word;
    padding-left: 12px;
}
"""


def _wrap_standalone_html(
    title: str, css: str, body: str
) -> str:
    """スタンドアロンHTML文書を組み立てる"""
    escaped_title = html.escape(title)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escaped_title}</title>
<style>
{_STANDALONE_BASE_CSS}
{css}
</style>
</head>
<body>
{body}
</body>
</html>"""


def export_matome_as_html(
    matome_data: dict[str, Any], output_path: Path
) -> Path:
    """まとめデータをスタンドアロンHTMLファイルに書き出す"""
    title = html.escape(str(matome_data.get("title", "まとめ")))
    category = html.escape(str(matome_data.get("category", "")))
    editor_comment = html.escape(
        str(matome_data.get("editor_comment", ""))
    )
    reactions = html.escape(
        str(matome_data.get("reactions_summary", ""))
    )
    now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    comments_count = len(matome_data.get("thread_comments", []))

    comments_html = ""
    for comment in matome_data.get("thread_comments", []):
        number = int(comment.get("number", 0))
        name = html.escape(str(comment.get("name", "名無しさん")))
        cid = html.escape(str(comment.get("id", "")))
        content = html.escape(str(comment.get("content", "")))
        is_highlighted = comment.get("is_highlighted", False)
        highlight_color = comment.get("highlight_color")

        css_class = "matome-res"
        if is_highlighted and highlight_color == "red":
            css_class += " hl-red"
        elif is_highlighted and highlight_color == "blue":
            css_class += " hl-blue"

        content = _decorate_anchors_css(content)
        fake_date = datetime.now().strftime("%y/%m/%d")
        fake_time = datetime.now().strftime("%H:%M:%S")
        ts = f"{fake_date}(土) {fake_time}"

        comments_html += f"""
    <div class="{css_class}">
      <div class="matome-res-header">
        <span class="matome-res-num">{number}:</span>
        <span class="matome-res-name">{name}</span>
        <span class="matome-res-timestamp">{ts} ID:{cid}</span>
      </div>
      <div class="matome-res-content">{content}</div>
    </div>"""

    editor_html = ""
    if editor_comment:
        editor_html = (
            f'\n  <div class="matome-editor-comment">'
            f"{editor_comment}</div>"
        )

    footer_html = ""
    if reactions:
        footer_html = (
            f'\n  <div class="matome-footer">{reactions}</div>'
        )

    body = f"""<div class="matome-wrap">
  <div class="matome-title-bar"><h2>{title}</h2></div>
  <div class="matome-meta">
    <span>{now_str}</span>
    <span class="meta-right">
      <span class="meta-category">カテゴリ：{category}</span>
      <span class="meta-comments">コメント({comments_count})</span>
    </span>
  </div>{editor_html}
  <div class="matome-body">{comments_html}
  </div>{footer_html}
  <div class="matome-source">このまとめはAIが自動生成しました</div>
</div>"""

    full_html = _wrap_standalone_html(
        title, _STANDALONE_MATOME_CSS, body
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full_html, encoding="utf-8")
    return output_path


def export_thread_as_html(
    thread_posts: list[dict[str, Any]],
    thread_title: str,
    total_count: int,
    output_path: Path,
) -> Path:
    """スレッド全レスをスタンドアロンHTMLファイルに書き出す"""
    escaped_title = html.escape(thread_title)

    posts_html = ""
    for post in thread_posts:
        number = post.get("number", 0)
        name = html.escape(str(post.get("name", "名無しさん")))
        display_id = html.escape(str(post.get("display_id", "")))
        date_str = html.escape(str(post.get("date_str", "")))
        content = html.escape(str(post.get("content", "")))
        content = _decorate_anchors_css(content)

        posts_html += f"""
      <div class="thread-post">
        <div class="thread-post-header">
          <span class="thread-post-number">{number}</span> ：
          <span class="thread-post-name">{name}</span>
          ：<span class="thread-post-date">{date_str}</span>
          <span class="thread-post-id">ID:{display_id}</span>
        </div>
        <div class="thread-post-content">{content}</div>
      </div>"""

    body = f"""<div class="thread-container">
  <div class="thread-header">
    {escaped_title}
    <br><small>このスレッドはAIが自動生成しています</small>
  </div>
  <div class="thread-posts">{posts_html}
  </div>
  <div class="thread-footer">
    このスレッドは{total_count}レスで終了しました。
  </div>
</div>"""

    full_html = _wrap_standalone_html(
        thread_title, _STANDALONE_THREAD_CSS, body
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full_html, encoding="utf-8")
    return output_path


def export_rawlog_as_html(
    raw_log_entries: list[dict[str, str]],
    output_path: Path,
) -> Path:
    """生ログをスタンドアロンHTMLファイルに書き出す"""
    entries_html = ""
    for entry in raw_log_entries:
        source = html.escape(str(entry.get("source", "")))
        content = html.escape(str(entry.get("content", "")))
        content = _decorate_anchors_css(content)

        entries_html += f"""
    <div class="rawlog-entry">
      <div class="rawlog-source">[{source}]</div>
      <div class="rawlog-content">{content}</div>
    </div>"""

    body = f"""<div class="rawlog-container">
  <div class="rawlog-header">議論 生ログ</div>
  <div class="rawlog-body">{entries_html}
  </div>
</div>"""

    full_html = _wrap_standalone_html(
        "生ログ", _STANDALONE_RAWLOG_CSS, body
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full_html, encoding="utf-8")
    return output_path
