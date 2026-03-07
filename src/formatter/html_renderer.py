"""まとめ風HTML/CSS生成モジュール

まとめエージェントの出力データを2chまとめサイト風のHTML文字列に変換する。
また、リアルタイムスレッド表示用のHTMLも生成する。
Gradioのgr.HTMLコンポーネントでは<style>タグが無視される場合があるため、
まとめ表示はインラインスタイルで記述する。
"""

import html
import re
from datetime import datetime
from typing import Any


def _decorate_anchors(text: str) -> str:
    """>>数字 形式のアンカーをスタイル付きspanに変換する"""
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


# ========================================
# まとめサイト風 HTML（インラインスタイル版）
# ========================================

# 共通フォント指定
_FONT = "'Hiragino Kaku Gothic ProN','メイリオ',Meiryo,sans-serif"


def render_matome_html(matome_data: dict[str, Any]) -> str:
    """まとめデータをHTML文字列に変換する（umamusume.net風デザイン）

    すべてのスタイルをインラインで記述し、
    Gradioのgr.HTMLコンポーネントで確実に表示する。

    Args:
        matome_data: まとめエージェントの出力辞書

    Returns:
        完全なHTMLフラグメント文字列
    """
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

    # レスHTML生成
    comments_html = ""
    for idx, comment in enumerate(matome_data.get("thread_comments", [])):
        number = int(comment.get("number", 0))
        name = html.escape(str(comment.get("name", "名無しさん")))
        cid = html.escape(str(comment.get("id", "")))
        content = html.escape(str(comment.get("content", "")))
        is_highlighted = comment.get("is_highlighted", False)
        highlight_color = comment.get("highlight_color")

        # レスの外枠スタイル
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

        # アンカー装飾
        content = _decorate_anchors(content)

        # 日時を疑似生成
        fake_date = datetime.now().strftime("%y/%m/%d")
        fake_time = datetime.now().strftime("%H:%M:%S")
        timestamp_str = f"{fake_date}(土) {fake_time}"

        # ヘッダースタイル
        header_style = (
            "font-size:0.82em;"
            "line-height:1.6;"
            "padding-top:14px;"
            "color:#333;"
        )
        num_style = "font-weight:bold;color:#333;"
        name_style = "color:#117743;font-weight:bold;"
        ts_style = "color:#999;margin-left:2px;"

        # 本文スタイル
        content_style = (
            "font-size:0.95em;"
            "line-height:1.7;"
            "color:#333;"
            "padding:10px 0 16px 0;"
            "margin:0;"
            "white-space:pre-wrap;"
            "word-wrap:break-word;"
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

    # 管理人コメント
    editor_html = ""
    if editor_comment:
        editor_html = (
            f'\n  <div style="padding:14px 20px;font-size:0.92em;'
            f"color:#333;line-height:1.7;"
            f'border-bottom:1px solid #eee;background:#fff;">'
            f"{editor_comment}</div>"
        )

    # フッター
    footer_html = ""
    if reactions:
        footer_html = (
            f'\n  <div style="padding:14px 20px;background:#f8f8f8;'
            f"border-top:1px solid #e0e0e0;font-size:0.85em;"
            f'color:#666;line-height:1.6;">'
            f"{reactions}</div>"
        )

    # 全体の組み立て
    wrap_style = (
        f"font-family:{_FONT};"
        "max-width:780px;"
        "margin:0 auto;"
        "background:#fff;"
        "border:1px solid #dcdcdc;"
        "border-radius:4px;"
        "overflow:hidden;"
    )

    title_bar_style = (
        "background:#fff;"
        "padding:14px 20px 12px;"
        "border-bottom:3px solid #ff6600;"
    )
    title_text_style = (
        "margin:0;padding:0;"
        "font-size:1.3em;"
        "font-weight:bold;"
        "line-height:1.45;"
        "color:#333;"
    )

    meta_style = (
        "display:flex;"
        "justify-content:space-between;"
        "align-items:center;"
        "padding:6px 20px;"
        "font-size:0.78em;"
        "color:#999;"
        "border-bottom:1px solid #eee;"
        "background:#fafafa;"
    )
    meta_right_style = "display:flex;gap:12px;"
    cat_style = "color:#ff6600;font-weight:bold;"
    count_style = "color:#ff6600;font-weight:bold;"

    source_style = (
        "padding:10px 20px;"
        "font-size:0.75em;"
        "color:#aaa;"
        "border-top:1px solid #f0f0f0;"
        "background:#fafafa;"
    )

    html_output = f"""<div style="{wrap_style}">
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

    return html_output


# ========================================
# スレッド風リアルタイム表示 HTML（インラインスタイル版）
# ========================================


def render_thread_header(title: str) -> str:
    """スレッドのヘッダー部分のHTMLを生成する"""
    escaped_title = html.escape(title)

    # スピナーアニメーションだけは<style>が必要
    # Gradioが<style>をブロックする場合のフォールバックとして
    # テキストベースのインジケーターも用意する
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
        "max-width:800px;"
        "margin:0 auto;"
        "background-color:#efefef;"
        "border:1px solid #aaa;"
    )
    header_style = (
        "background-color:#800000;"
        "color:#fff;"
        "padding:8px 12px;"
        "font-size:1.1em;"
        "font-weight:bold;"
    )
    small_style = (
        "font-weight:normal;"
        "font-size:0.8em;"
        "color:#ffcccc;"
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
        "font-size:0.95em;"
        "line-height:1.5;"
        "color:#000;"
        "padding:2px 0 6px 20px;"
        "white-space:pre-wrap;"
        "word-wrap:break-word;"
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
        "text-align:center;"
        "padding:12px;"
        "color:#666;"
        "font-size:0.9em;"
    )
    spinner_style = (
        "display:inline-block;"
        "width:16px;"
        "height:16px;"
        "border:2px solid #ccc;"
        "border-top-color:#800000;"
        "border-radius:50%;"
        "animation:spin-thread 0.8s linear infinite;"
        "vertical-align:middle;"
        "margin-right:6px;"
    )

    return f"""
    <div style="{loading_style}">
      <span style="{spinner_style}"></span>
      レスを書き込み中... ({current}/{total})
    </div>"""


def render_thread_footer(total: int) -> str:
    """スレッドのフッター部分のHTMLを生成する"""
    footer_style = (
        "background-color:#800000;"
        "color:#fff;"
        "padding:8px 12px;"
        "font-size:0.85em;"
        "font-weight:normal;"
    )
    return f"""
  </div>
  <div style="{footer_style}">
    このスレッドは{total}レスで終了しました。
  </div>
</div>"""
