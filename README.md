# 2ch/5chまとめ風ジェネレーター

ユーザーが入力したテーマに基づき、複数のAIエージェントが2ちゃんねらー風に議論を行い、
その結果を「まとめサイト風」に自動編集するWebアプリケーションです。

## 必要環境

- macOS（Apple Silicon対応）
- Python 3.10以上
- uv（パッケージマネージャー）

## セットアップ手順

```bash
# 1. リポジトリをクローンまたはダウンロード
cd matome-site-generator

# 2. 設定ファイルを準備
cp config/settings.yaml.example config/settings.yaml
# settings.yaml をテキストエディタで開き、APIキーを入力してください

# 3. 依存パッケージをインストール
uv sync

# 4. アプリを起動
uv run matome-site-generator

# 5. ブラウザで http://127.0.0.1:7860 にアクセス
```

## 対応LLMプロバイダー

| プロバイダー | 説明 | 設定箇所 |
|---|---|---|
| OpenAI | GPT-4o, GPT-4o-mini 等（APIキー必要） | `api_keys.openai` |
| Gemini | Google Gemini（APIキー必要、OpenAI互換API経由） | `api_keys.gemini` |
| Ollama | ローカルLLM（Ollamaサーバー起動が必要） | `local_servers.ollama_base_url` |
| LM Studio | ローカルLLM（LM Studioサーバー起動が必要） | `local_servers.lmstudio_base_url` |
| OpenRouter | 数百種類のモデルに統一APIでアクセス（APIキー必要） | `api_keys.openrouter` |
| カスタムOpenAI互換 | Together AI, Groq, Fireworks 等、任意のOpenAI互換API | `custom_openai` セクション |

## 設定ファイル

`config/settings.yaml` にAPIキーやデフォルト設定を記述します。
詳細は `config/settings.yaml.example` を参照してください。

### OpenRouter の使い方

1. [OpenRouter](https://openrouter.ai/) でアカウントを作成し、APIキーを取得
2. `config/settings.yaml` の `api_keys.openrouter` にキーを設定
3. UI の「議論用LLMプロバイダー」で `openrouter` を選択
4. モデル名は `openai/gpt-4o-mini` のように「プロバイダー/モデル名」形式で入力

### カスタムOpenAI互換プロバイダーの使い方

OpenAI互換APIを提供する任意のサービスに接続できます。

1. `config/settings.yaml` の `custom_openai` セクションに `base_url` と `api_key` を設定（またはUI上で入力）
2. UI の「議論用LLMプロバイダー」で `custom_openai` を選択
3. モデル名に接続先サービスのモデル名を入力

UI上で入力したベースURLやAPIキーは `settings.yaml` の値より優先されます。
