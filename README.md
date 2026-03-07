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
uv run python src/app.py

# 5. ブラウザで http://127.0.0.1:7860 にアクセス
```

## 対応LLMプロバイダー

| プロバイダー | 説明 |
|---|---|
| OpenAI | GPT-4o, GPT-4o-mini 等（APIキー必要） |
| Gemini | Google Gemini（APIキー必要、OpenAI互換API経由） |
| Ollama | ローカルLLM（Ollamaサーバー起動が必要） |
| LM Studio | ローカルLLM（LM Studioサーバー起動が必要） |

## 設定ファイル

`config/settings.yaml` にAPIキーやデフォルト設定を記述します。
詳細は `config/settings.yaml.example` を参照してください。
