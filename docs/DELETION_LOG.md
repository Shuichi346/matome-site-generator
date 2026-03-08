# Code Deletion Log

## 2026-03-08

### Unused Dependencies Removed

- `pyproject.toml` から未使用の `Pillow>=10.0` を削除しました。

### Unused Files Deleted

- ルートの `.DS_Store` を削除しました。
- `src/.DS_Store` を削除しました。
- 未参照の `src/templates/matome.css` を削除しました。
- 不要な `config/.gitkeep` を削除しました。
- 不要な `tests/.gitkeep` を削除しました。

### Duplicate Code Consolidated

- `src/app.py` の組み込みプリセット定義を削除し、`config/presets.json` を唯一の保存元に統一しました。
- `generate_matome_streaming()` と `save_settings_from_ui()` に重複していた UI 設定保存用辞書を `_build_ui_settings_payload()` に集約しました。
- 起動処理を `main()` にまとめ、console script から起動できるように整理しました。

### Unused Exports Removed

- 今回は削除なしです。

### Do Not Remove Yet

- `src/agents/discussion.py` の `run_discussion` はリポジトリ内で未参照でしたが、非ストリーミング実行用の公開APIになり得るため保留にしました。
- `src/formatter/text_exporter.py` の `export_as_text` は後方互換用エイリアスのため保留にしました。
- `src/formatter/json_exporter.py` の `export_as_json` は後方互換用エイリアスのため保留にしました。

### Impact

- 未使用グローバル `_current_discussion_agents` を削除し、停止制御の状態管理を簡潔にしました。
- プリセットの読み込み失敗時は空のプリセット一覧にフォールバックするようにして、重複定義をなくしました。
- `fetch_multiple_urls()` を `asyncio.gather()` ベースに変更し、入力順を保ったまま並列取得できるようにしました。
- `generate_thread_title()` と `run_summarizer()` は途中例外時でもモデルクライアントを閉じるようにしました。

### Testing

- 作業前に `uvx deptry .`、`uvx vulture src --min-confidence 80`、`uvx ruff check . --select F401,F841` を実行し、依存・未使用コード・未使用 import を確認しました。
- 作業後に `uv sync`、`uvx ruff check .`、`uvx deptry .`、`uvx vulture src --min-confidence 80`、`uv run python -m compileall src`、import スモークテスト、`main` 存在確認を実行しました。
- 最終結果は `ruff` 正常終了、`deptry` 正常終了、`vulture` 指摘なし、`compileall` 正常終了、import スモークテスト `import ok`、`main` 存在確認 `True` でした。
