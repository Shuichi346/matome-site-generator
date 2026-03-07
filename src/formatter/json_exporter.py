"""JSON形式エクスポートモジュール

まとめ結果・スレッドログ・生ログを整形JSON(.json)形式で出力する。
"""

import json
from pathlib import Path
from typing import Any


def _write_json(data: Any, output_path: Path) -> Path:
    """共通のJSON書き出し処理"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    output_path.write_text(json_text, encoding="utf-8")
    return output_path


def export_matome_as_json(
    matome_data: dict[str, Any], output_path: Path
) -> Path:
    """まとめデータをJSONファイルに書き出す"""
    return _write_json(matome_data, output_path)


def export_thread_as_json(
    thread_posts: list[dict[str, Any]],
    thread_title: str,
    output_path: Path,
) -> Path:
    """スレッドの全レスをJSONファイルに書き出す

    Args:
        thread_posts: レスのリスト
        thread_title: スレッドタイトル
        output_path: 出力先ファイルパス
    """
    data = {
        "thread_title": thread_title,
        "posts": thread_posts,
    }
    return _write_json(data, output_path)


def export_rawlog_as_json(
    raw_log_entries: list[dict[str, str]],
    output_path: Path,
) -> Path:
    """生ログをJSONファイルに書き出す

    Args:
        raw_log_entries: 生ログエントリのリスト（各要素はsource, content）
        output_path: 出力先ファイルパス
    """
    data = {
        "raw_log": raw_log_entries,
    }
    return _write_json(data, output_path)


# 後方互換のエイリアス
def export_as_json(
    matome_data: dict[str, Any], output_path: Path
) -> Path:
    """後方互換用: export_matome_as_jsonへの委譲"""
    return export_matome_as_json(matome_data, output_path)
