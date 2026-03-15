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

## 2026-03-09

### LM Studio プロバイダーの削除

- `src/models/client_factory.py` から LM Studio プロバイダーを削除しました。
- `ALL_PROVIDERS` リストから `"lmstudio"` を削除しました。
- `create_model_client()` の `lmstudio_url` 引数を削除しました。
- `src/app.py` から LM Studio 関連の UI 要素（URL入力欄）を削除しました。
- `src/app.py` の全関数シグネチャから `lmstudio_url` 引数を削除しました。
- `_DEFAULT_PROVIDER_MODELS` と `_DEFAULT_SUM_PROVIDER_MODELS` から `"lmstudio"` を削除しました。
- `_DEFAULT_UI_SETTINGS` から `"lmstudio_url"` を削除しました。
- `_load_ui_settings()` で古い `lmstudio_url` 設定を無視するようにしました。
- `config/settings.yaml.example` から `lmstudio_base_url` を削除しました。
- `README.md` から LM Studio 関連の記述を削除しました。
- `src/agents/discussion.py` と `src/agents/summarizer.py` から `lmstudio_url` 引数を削除しました。

### Ollama Thinking 設定の追加

- `src/models/client_factory.py` の `create_model_client()` に `ollama_think` 引数を追加しました。
- `OllamaChatCompletionClient` に `think` パラメータを渡し、Ollama API の `ChatRequest.think` に転送する設計です。
- `src/agents/discussion.py` の `build_discussion_agents()` に `ollama_think` 引数を追加しました。
- `src/agents/summarizer.py` の `generate_thread_title()` と `run_summarizer()` に `ollama_think` 引数を追加しました。
- `src/app.py` に議論用・まとめ用のthinking設定UIを追加しました。
- `config/settings.yaml.example` に `ollama.discussion_think` と `ollama.summarizer_think` を追加しました。
- UI設定（`ui_settings.json`）に `ollama_disc_think` と `ollama_sum_think` を追加しました。

### 削除理由

LM Studio は API レベルで thinking を制御する公式手段がなく、`<think>` ブロック関連のバグが複数報告されているため、ローカル LLM は Ollama に一本化しました。Ollama は v0.9.0 以降で `think` パラメータを公式サポートしており、API レベルで確実に thinking の ON/OFF を制御できます。

### Testing

- `uv sync`、`uv run python -m compileall src`、import スモークテストを実行しました。
- `uv sync` は正常終了しました。
- `uv run python -m compileall src` は正常終了しました。
- import スモークテストでは `src` 配下の 15 モジュールを import し、問題ありませんでした。

### レス番号の履歴埋め込み

- `src/agents/discussion.py` に `_stamp_res_numbers()` 関数を追加しました。
- 各メッセージの本文先頭に `[現在のレス番号: >>N]` を付与し、モデルが実際のレス番号を参照できるようにしました。
- `RateLimitedAssistantAgent` に `_prepare_messages()` メソッドを追加しました。
- 処理順は「レス番号付与 → トリミング」とし、間引き後も実際の表示レス番号が保持される設計です。
- `on_messages()` と `on_messages_stream()` の内部呼び出しを `_trim_messages()` から `_prepare_messages()` に変更しました。
- `tests/test_discussion.py` にレス番号付与のテストを5件追加しました（`test_stamp_res_numbers_basic`、`test_stamp_res_numbers_empty`、`test_prepare_preserves_real_numbers_after_trim`、`test_prepare_no_trim_all_numbers_sequential`、`test_prepare_large_trim_keeps_real_numbers`）。

### 修正理由

Ollamaで実行した際に `>>1257` のような見当違いのアンカーが生成されていました。原因は、各エージェントに渡される会話履歴にレス番号情報が含まれておらず、モデルが「今が何レス目か」「直前のレスが何番か」を把握できなかったためです。

### Testing

- `uv run python -m compileall src tests` は正常終了しました。
- `uv run pytest` は 21 件全て passed でした。

## 2026-03-10

### アンカー偏りの根本修正

- `src/agents/discussion.py` の `RateLimitedAssistantAgent` を修正しました。
- これまでは、各ターンでモデルに渡された**差分メッセージだけ**に `_stamp_res_numbers()` を適用していたため、各エージェント視点で毎回 `>>1` 〜 `>>4` 前後の**局所的な番号**が繰り返し見えていました。
- その結果、5人前後のラウンドロビン議論では、各エージェントが次の自分の番までに受け取る新着がほぼ4件になるため、`>>4` が不自然に頻発する不具合が発生していました。
- 修正後は、各エージェントが `_message_history` に**累積履歴**を保持し、その全履歴に対してレス番号を付与してからトリミングする方式に変更しました。
- `AssistantAgent` 内部に古い誤番号付き履歴が残り続けないよう、各ターンで `_inner_agent.on_reset()` を呼び、毎回クリーンな状態で整形済み履歴を渡す設計に変更しました。
- `on_messages_stream()` では、最終 `Response` が返らない経路でも最後の `TextMessage` を履歴へ保存するようにして、履歴欠落を防ぐようにしました。

### テスト追加・更新

- `tests/test_discussion.py` の `_build_agent()` に `_message_history` の初期化を追加しました。
- 累積履歴に対してグローバルなレス番号が維持されることを確認するテストを2件追加しました。
  - `test_prepare_history_messages_keeps_global_numbers_across_turns`
  - `test_prepare_history_messages_with_trim_keeps_real_numbers`

### 修正理由

- 問題の本質はプロンプト文言ではなく、**会話履歴の持ち方とレス番号付与の単位**にありました。
- `persona.py` 側の「アンカーを必須にしない」「同じアンカー先を繰り返さない」といった調整は補助策として有効ですが、今回の `>>4` 偏重の主因ではありませんでした。
- 根本対策としては、**差分ではなく累積履歴ベースで番号付与すること**が必要でした。

### Impact

- `>>4` のような同一アンカー先の不自然な連発が起きにくくなりました。
- `max_context_messages` を使って履歴を間引いた場合でも、残ったメッセージに**実際の通しレス番号**が保持されるようになりました。
- 内部状態と外部に渡す履歴の責務が明確になり、今後の保守性も向上しました。

### Testing

- `uv run pytest tests/test_discussion.py -q` を実行し、`12 passed` を確認しました。
- `uv run pytest -q` を実行し、`24 passed` を確認しました。
- `uv run python -m compileall src tests` を実行し、正常終了を確認しました。

## 2026-03-15

### 議論パートのチャットパターン切替機能の追加

- `src/agents/discussion.py` に `SelectorGroupChat` のインポートを追加しました。
- セレクタープロンプト定数 `SELECTOR_PROMPT` を日本語で定義しました。
- チャットパターン定数 `CHAT_PATTERN_ROUND_ROBIN` / `CHAT_PATTERN_SELECTOR` を定義しました。
- `_normalize_chat_pattern()` ヘルパーを追加しました。
- `_build_group_chat()` 関数を新設し、`chat_pattern` に応じて `RoundRobinGroupChat` または `SelectorGroupChat` を返すようにしました。
- `_close_model_client()` ヘルパーを追加しました。
- `run_discussion()` と `run_discussion_stream()` に `chat_pattern` と `selector_model_client` 引数を追加しました。
- セレクター用モデルクライアントは `finally` 節で閉じるようにしました。
- `src/app.py` に `CHAT_PATTERN_ROUND_ROBIN` / `CHAT_PATTERN_SELECTOR` / `create_model_client` のインポートを追加しました。
- `_CHAT_PATTERN_CHOICES` を定義しました。
- `_DEFAULT_UI_SETTINGS` に `chat_pattern` を追加しました。
- `_load_ui_settings()` で `defaults.chat_pattern` を読み込むようにしました。
- `_build_ui_settings_payload()` に `chat_pattern` 引数を追加しました。
- `_create_selector_model_client()` ヘルパーを新設しました。
- `generate_matome_streaming()` に `chat_pattern` 引数を追加し、`selector` の場合はまとめ用プロバイダー・モデルでセレクタークライアントを生成して `run_discussion_stream()` に渡すようにしました。
- `save_settings_from_ui()` に `chat_pattern` 引数を追加しました。
- 詳細設定タブに「議論パートのチャットパターン」ドロップダウンを追加しました。
- 生成ボタン・設定保存ボタンの `inputs` に `chat_pattern_input` を追加しました。
- `config/settings.yaml.example` の `defaults` セクションに `chat_pattern: "selector"` を追加しました。
- `tests/test_app.py` に `CHAT_PATTERN_ROUND_ROBIN` のインポートを追加し、`_base_kwargs()` に `chat_pattern` を追加しました。
- `tests/test_image_analyzer.py` に `CHAT_PATTERN_ROUND_ROBIN` のインポートを追加し、`generate_matome_streaming()` の呼び出しに `chat_pattern` 引数を追加しました。

### 設計判断

- `SelectorGroupChat` の `model_client` にはまとめ用プロバイダー・モデルを使用しました。セレクターLLMは「文脈を読んで次の発言者を判断する」役割のため、性能の良いモデルが適しています。議論用は軽量・高速モデルを選ぶことが多いため不向きと判断しました。
- `allow_repeated_speaker=True` に設定し、同じエージェントの連続発言を許可しました。掲示板では同一人物が連投することは自然なためです。
- デフォルトは `selector`（SelectorGroupChat）としました。
- `round_robin` を選択した場合は、`selector_model_client` を生成せず従来と完全に同じ `RoundRobinGroupChat` 動作になります。

### Impact

- 議論パートの発言順がLLMによる動的選択に対応し、掲示板らしい自然な会話の流れが実現できるようになりました。
- `round_robin` 選択時は既存動作と完全に同一であり、既存機能への影響はありません。
- レートリミッター、停止制御、ストリーミング表示、レス番号付与など既存の仕組みは変更していません。

### Testing

- `uv run python -m compileall src tests` を実行し、正常終了を確認しました。
- `uv run pytest -q` を実行し、`24 passed` を確認しました。

## 2026-03-15 (2)

### 自分自身の投稿へのアンカー防止

- `src/agents/discussion.py` に `_extract_display_id_from_source()` ヘルパーを追加しました。エージェントの `source` 名（`agent_{index}_{display_id}` 形式）から掲示板表示用の `display_id` を抽出します。
- `_stamp_res_numbers()` のスタンプフォーマットを `[現在のレス番号: >>N]` から `[レス番号: >>N / 投稿者ID: XXXXXXXX]` に変更しました。モデルが各レスの投稿者を識別できるようにするためです。
- `RateLimitedAssistantAgent` に `display_id` 属性を追加しました。
- `build_discussion_agents()` で各エージェント生成時に `display_id=persona.display_id` を渡すようにしました。
- `src/agents/persona.py` の `build_system_prompt()` に以下の変更を加えました。
  - ルールに「自分自身の投稿（投稿者IDが {自分のID} のレス）には絶対にアンカーを打たない」を追加しました。
  - 新セクション「自分の投稿の見分け方」を追加し、投稿者IDの確認方法と自分以外のIDにのみアンカーを打つ指示を明記しました。
- `tests/test_discussion.py` を新フォーマットに合わせて更新しました。
  - `_build_messages()` の `source` を `agent_{index}_src{index:04d}` 形式に変更しました。
  - `_build_agent()` に `_display_id` の初期化を追加しました。
  - `_extract_display_id_from_source` のテストを2件追加しました（`test_extract_display_id_standard_format`、`test_extract_display_id_non_standard_format`）。
  - `_stamp_res_numbers` の非agent形式sourceに対するテストを1件追加しました（`test_stamp_res_numbers_non_agent_source`）。
  - 既存テストのアサーションを新フォーマット `[レス番号: >>N / 投稿者ID: XXXXXXXX]` に更新しました。

### 修正理由

- 各エージェントが過去のレスを参照する際、「どのレスが自分の投稿か」を区別する情報がレス番号スタンプに含まれていませんでした。
- そのため、例えば3投稿目で「AI風吹けば名無し」が投稿した後、同じ「AI風吹けば名無し」が `>>3` にアンカーを打って批判するという不自然な挙動が発生していました。
- コード側で投稿者IDをスタンプに含め、プロンプト側で自分のIDを明示して自己返信を禁止することで、両面から抑制しました。

### Impact

- 自分自身の投稿にアンカーを打つ不自然な挙動が解消されました。
- レス番号スタンプに投稿者ID情報が追加されたことで、モデルが投稿者を正確に識別できるようになりました。
- プロンプトに自分のIDを明示したことで、アンカー対象の判断精度が向上しました。
- `app.py` への変更はなく、既存の呼び出しコードに影響はありません。

### Testing

- `uv run pytest -q` を実行し、`28 passed` を確認しました。
- `uv run python -m compileall src tests` を実行し、正常終了を確認しました。