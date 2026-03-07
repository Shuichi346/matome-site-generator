"""JSON形式エクスポートモジュール

まとめ結果を整形JSON(.json)形式で出力する。
"""

import json
from pathlib import Path
from typing import Any


def export_as_json(matome_data: dict[str, Any], output_path: Path) -> Path:
    """まとめデータをJSONファイルに書き出す

    Args:
        matome_data: まとめの構造化データ
        output_path: 出力先ファイルパス

    Returns:
        書き出したファイルのパス
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(matome_data, ensure_ascii=False, indent=2)
    output_path.write_text(json_text, encoding="utf-8")
    return output_path
