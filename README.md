# 2ch/5chまとめ風ジェネレーター

入力したテーマをもとに、複数のAIエージェントが匿名掲示板風に議論し、その流れを「まとめサイト風」の記事へ自動整形する Web アプリです。

議論パートと要約パートで別モデルを使えます。URL参照、Web検索、添付ファイル、添付画像の解析、プリセット保存、途中停止、ZIP一括ダウンロードに対応しています。

## 主な機能

- 複数のAIエージェントによる 2ch / 5ch 風の議論生成
- 議論ログからスレッドタイトルとまとめ記事を自動生成
- 参考URL取得と DuckDuckGo Web検索による補足情報の取り込み
- 添付テキストファイルの取り込み
- 添付画像を vision 対応LLMで解析し、議論コンテキストへ反映
- スレッド表示、まとめ表示、生ログ表示
- `txt` / `json` / `html` の 3形式で出力し、9ファイルを ZIP にまとめて保存
- 詳細設定タブでプロバイダー、モデル、待機時間、検索設定、会話履歴設定を保存
- Ollama の thinking（推論）モードを議論用・まとめ用で個別にON/OFF可能
- テーマプリセット保存、途中停止、進捗表示、時間見積もり

## 必要環境

- macOS
- Python 3.10 以上
- `uv`

補足:

- Apple Silicon を想定しています
- Ollama は使う場合のみ別途起動が必要です

## セットアップ

```bash
# 1. リポジトリを配置
cd matome-site-generator

# 2. 設定ファイルを作成
cp config/settings.yaml.example config/settings.yaml

# 3. 依存パッケージをインストール
uv sync

# 4. アプリを起動
uv run matome-site-generator
```

起動後、ブラウザで [http://127.0.0.1:7860](http://127.0.0.1:7860) を開いてください。

## 対応LLMプロバイダー

| プロバイダー | 用途 | 主な設定 |
|---|---|---|
| `openai` | OpenAI API | `api_keys.openai` |
| `gemini` | Gemini API | `api_keys.gemini` |
| `ollama` | ローカルLLM（thinking制御対応） | `local_servers.ollama_base_url` |
| `openrouter` | OpenRouter 経由の各種モデル | `api_keys.openrouter`, `openrouter.base_url` |
| `custom_openai` | 任意の OpenAI 互換 API | `custom_openai.base_url`, `custom_openai.api_key` |

## 設定ファイル

`config/settings.yaml` に API キーや接続先を記述します。ひな形は [config/settings.yaml.example](config/settings.yaml.example) です。

主なセクション:

- `api_keys`
  - `openai`
  - `gemini`
  - `openrouter`
- `local_servers`
  - `ollama_base_url`
- `ollama`
  - `discussion_think` — 議論用のthinking設定（true/false/未指定）
  - `summarizer_think` — まとめ用のthinking設定（true/false/未指定）
  - `model_info` — Ollamaモデルの能力設定。画像を使う場合は `vision: true` が必要
- `openrouter`
  - `base_url`
- `custom_openai`
  - `base_url`
  - `api_key`
  - `model_info`
- `defaults`
  - 議論用 / まとめ用モデル、待機時間
- `web_fetch`
  - Web検索・URL取得のデフォルト

`web_fetch` では次の 3 項目を設定できます。

```yaml
web_fetch:
  max_search_results: 3
  max_url_content_length: 2000
  search_content_mode: "snippet"
```

意味:

- `max_search_results`: Web検索で取得する件数
- `max_url_content_length`: 各URL本文の最大文字数
- `search_content_mode`: Web検索結果の取得モード。`snippet` ならスニペット中心、`full` なら検索結果本文も取得

補足:

- テーマ欄、補足欄、参考URL欄に手入力したURLは常に本文を取得します
- `search_content_mode` は DuckDuckGo の検索結果にだけ適用されます

## Ollama Thinking（推論）モードについて

Qwen3 や DeepSeek-R1 などの thinking 対応モデルでは、Ollama の `think` パラメータで推論モードを制御できます。

設定方法は2つあります:

### 1. UIから設定（推奨）

詳細設定タブの「Ollama Thinking設定」で、議論用・まとめ用それぞれに設定できます。

- **ON**: thinking を有効化（精度が向上するが応答が遅くなる）
- **OFF**: thinking を無効化（高速応答）
- **モデルのデフォルト**: モデル側の既定動作に従う

### 2. settings.yaml から設定

```yaml
ollama:
  discussion_think: false    # 議論用
  summarizer_think: true     # まとめ用
  model_info:
    vision: false
    function_calling: false
    json_output: true
    structured_output: false
```

UI設定が `settings.yaml` より優先されます。

画像添付を使う場合は、議論用モデルが vision 対応である必要があります。`ollama` と `custom_openai` は `model_info.vision` で判定します。

### 推奨設定

- 議論用: **OFF**（各レスの生成速度を重視）
- まとめ用: **ON** または **OFF**（まとめ品質を重視するならON）

## 基本的な使い方

1. 「テーマ」に議論させたい内容を入力します。
2. 必要なら「方向性・補足情報」を入力します。
3. 必要なら参考URL、検索キーワード、添付ファイル、画像を追加します。
4. 議論回数、参加人数、トーン、利用モデルを設定します。
5. 「生成」を押すと、スレッド、まとめ、ログが順に作られます。
6. 完了まで進んだ場合は ZIP をダウンロードできます。

補足:

- スレッドタイトルは AI が自動生成します
- 画像を添付すると、議論開始前に vision 対応LLM が画像内容を解析して議論へ反映します
- vision 非対応モデルでは画像添付は使えません
- 「中止」は以後の新しい重い処理を始めない停止要求です
- 中止時は途中までのスレッド表示が残りますが、状況によってはまとめやZIPは生成されません
- 詳細設定タブの内容は保存できます

## トークン節約のための設定

最新版では、LLM API のトークン消費を抑えるための設定を強化しています。

### 1. Web検索の取得量を減らす

詳細設定タブの「Web検索・URL取得設定」を使います。

- `Web検索の取得件数`
  - 小さいほどトークンを節約できます
- `URL本文の最大文字数`
  - 小さいほど各URLの取り込み量を減らせます
- `検索結果の取得モード`
  - `snippet`: Web検索結果はタイトルとスニペット中心で軽量
  - `full`: Web検索結果の本文も取得

手入力した参考URLは、`snippet` モードでも常に本文を取得します。

通常は `snippet` が推奨です。

### 2. 会話履歴を制限する

詳細設定タブの「エージェントに渡す会話履歴の最大件数」で、各エージェントが参照する履歴数を制限できます。

- `0`: 制限なし
- `10` 前後: 省トークンと文脈維持のバランスが取りやすい設定

この制限では、最初のタスクメッセージは常に保持しつつ、直近の会話を優先して渡します。

### 3. Ollama Thinking を OFF にする

thinking（推論）モードが ON だとモデルが内部で長く考えるため、トークンを多く消費します。議論用は OFF にするのが効率的です。

### 4. Web取得結果をシステムプロンプトへ入れすぎない

補足の Web 取得結果は、議論のシステムプロンプトには直接入れず、実際の議論タスク側で参照する設計です。これにより、各エージェントの固定プロンプト肥大化を抑えています。

## 詳細設定タブでできること

- 議論用LLMとまとめ用LLMを別々に設定
- APIウェイトタイムの調整
- Ollama Thinking の ON/OFF（議論用・まとめ用 個別）
- Ollama / OpenRouter / カスタムOpenAI互換の接続先指定
- Web検索件数、URL本文長、検索モードの調整
- 会話履歴の最大件数の調整
- 現在の設定を保存

保存先:

- UI設定: `config/ui_settings.json`
- テーマプリセット: `config/presets.json`

## OpenRouter の使い方

1. [OpenRouter](https://openrouter.ai/) で API キーを取得します。
2. `config/settings.yaml` の `api_keys.openrouter` を設定します。
3. 必要なら `openrouter.base_url` も設定します。
4. UI で `openrouter` を選び、モデル名に `openai/gpt-5-mini` のような形式を入力します。

## カスタムOpenAI互換プロバイダーの使い方

Together AI、Groq、Fireworks、自社プロキシなど、OpenAI 互換 API に接続できます。

1. `config/settings.yaml` の `custom_openai.base_url` を設定します。
2. 必要なら `custom_openai.api_key` を設定します。
3. UI で `custom_openai` を選び、モデル名を入力します。

UI 上で入力したベース URL と API キーは、`settings.yaml` の値より優先されます。

## 出力ファイル

生成完了後、次の 3 種類がそれぞれ `txt` / `json` / `html` で保存されます。

- スレッド
- まとめ
- 生ログ

通常完了時は合計 9 ファイルを ZIP にまとめてダウンロードできます。中止した場合は、途中成果のみ表示されて ZIP が作られないことがあります。出力先ディレクトリは `output/` です。

## よくある調整

- レートリミットエラーが出る
  - `APIウェイトタイム` を 3 秒以上に増やしてください
- 生成コストを下げたい
  - `snippet` モード
  - `Web検索の取得件数` を 3 以下
  - `URL本文の最大文字数` を 2000 前後
  - `会話履歴の最大件数` を 10 前後
  - Ollama Thinking を OFF
- ローカルモデルを使いたい
  - Ollama サーバーを先に起動してください

## ライセンス

[LICENSE](LICENSE) を参照してください。
