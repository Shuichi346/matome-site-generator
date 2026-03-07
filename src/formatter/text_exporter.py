"""テキスト形式エクスポートモジュール

まとめ結果・スレッドログ・生ログをプレーンテキスト(.txt)形式で出力する。
"""

from pathlib import Path
from typing import Any


def export_matome_as_text(
    matome_data: dict[str, Any], output_path: Path
) -> Path:
    """まとめデータをテキストファイルに書き出す"""
    lines: list[str] = []

    title = matome_data.get("title", "まとめ")
    category = matome_data.get("category", "")
    editor_comment = matome_data.get("editor_comment", "")
    reactions = matome_data.get("reactions_summary", "")

    lines.append(f"【スレッドタイトル】{title}")
    lines.append(f"【カテゴリ】{category}")
    lines.append(f"【管理人コメント】{editor_comment}")
    lines.append("")
    lines.append("=" * 50)
    lines.append("")

    for comment in matome_data.get("thread_comments", []):
        number = comment.get("number", 0)
        name = comment.get("name", "名無しさん")
        cid = comment.get("id", "")
        content = comment.get("content", "")
        highlighted = " ★" if comment.get("is_highlighted") else ""

        lines.append(f"{number} 名前: {name} ID:{cid}{highlighted}")
        lines.append(content)
        lines.append("")

    lines.append("=" * 50)
    lines.append(f"【まとめ】{reactions}")

    text = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return output_path


def export_thread_as_text(
    thread_posts: list[dict[str, Any]],
    thread_title: str,
    output_path: Path,
) -> Path:
    """スレッドの全レスをテキストファイルに書き出す

    Args:
        thread_posts: レスのリスト（各要素はnumber, name, display_id, date_str, content）
        thread_title: スレッドタイトル
        output_path: 出力先ファイルパス
    """
    lines: list[str] = []
    lines.append(thread_title)
    lines.append("=" * 50)
    lines.append("")

    for post in thread_posts:
        number = post.get("number", 0)
        name = post.get("name", "名無しさん")
        display_id = post.get("display_id", "")
        date_str = post.get("date_str", "")
        content = post.get("content", "")

        lines.append(
            f"{number} 名前: {name} {date_str} ID:{display_id}"
        )
        lines.append(content)
        lines.append("")

    text = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return output_path


def export_rawlog_as_text(
    raw_log_lines: list[str], output_path: Path
) -> Path:
    """生ログをテキストファイルに書き出す

    Args:
        raw_log_lines: 生ログ文字列のリスト（各要素は「[source]\\ncontent\\n」形式）
        output_path: 出力先ファイルパス
    """
    text = "\n".join(raw_log_lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return output_path


# 後方互換のエイリアス
def export_as_text(
    matome_data: dict[str, Any], output_path: Path
) -> Path:
    """後方互換用: export_matome_as_textへの委譲"""
    return export_matome_as_text(matome_data, output_path)
