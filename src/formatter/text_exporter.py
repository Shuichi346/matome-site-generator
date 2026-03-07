"""テキスト形式エクスポートモジュール

まとめ結果をプレーンテキスト(.txt)形式で出力する。
"""

from pathlib import Path
from typing import Any


def export_as_text(matome_data: dict[str, Any], output_path: Path) -> Path:
    """まとめデータをテキストファイルに書き出す

    Args:
        matome_data: まとめの構造化データ
        output_path: 出力先ファイルパス

    Returns:
        書き出したファイルのパス
    """
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
