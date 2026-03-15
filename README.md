<table>
  <thead>
    <tr>
      <th style="text-align:center"><a href="README_en.md">English</a></th>
      <th style="text-align:center"><a href="README.md">日本語</a></th>
    </tr>
  </thead>
</table>

<p align="center">
  <strong>2ch/5chまとめ風ジェネレーター</strong>
</p>

<p align="center">
  複数のAIエージェントが匿名掲示板風に議論し、「まとめサイト風」記事を自動生成するWebアプリ
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Gradio-6.x-orange?logo=gradio" alt="Gradio 6">
  <img src="https://img.shields.io/badge/AutoGen-0.4.x-green" alt="AutoGen 0.4">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="MIT License">
  <img src="https://img.shields.io/badge/platform-macOS%20(Apple%20Silicon)-lightgrey?logo=apple" alt="macOS">
</p>

---

## 目次

- [概要](#概要)
- [主な機能](#主な機能)
- [技術スタック](#技術スタック)
- [必要環境](#必要環境)
- [セットアップ](#セットアップ)
- [基本的な使い方](#基本的な使い方)
- [対応LLMプロバイダー](#対応llmプロバイダー)
- [設定ファイル](#設定ファイル)
- [議論パートのチャットパターン](#議論パートのチャットパターン)
- [Ollama Thinking（推論）モード](#ollama-thinking推論モード)
- [トークン節約のための設定](#トークン節約のための設定)
- [詳細設定タブでできること](#詳細設定タブでできること)
- [OpenRouter の使い方](#openrouter-の使い方)
- [カスタムOpenAI互換プロバイダーの使い方](#カスタムopenai互換プロバイダーの使い方)
- [出力ファイル](#出力ファイル)
- [テスト](#テスト)
- [プロジェクト構成](#プロジェクト構成)
- [よくある調整](#よくある調整)
- [ライセンス](#ライセンス)

---

## 概要

**matome-site-generator** は、入力したテーマをもとに複数のAIエージェントが2ちゃんねる/5ちゃんねる風の匿名掲示板スタイルで議論を行い、その議論ログを「まとめサイト風」の記事へ自動整形するWebアプリケーションです。

議論パートとまとめパートで異なるLLMモデルを使い分けることができ、URL参照、DuckDuckGo Web検索、添付ファイル・画像の解析、テーマプリセットの保存、途中停止、ZIP一括ダウンロードなど、実用的な機能を幅広く備えています。

議論パートでは `SelectorGroupChat`（LLMが文脈に応じて次の発言者を動的に選択）と `RoundRobinGroupChat`（固定順で順番に発言）の2つのチャットパターンを切り替えて使用できます。

---

## 主な機能

- **2ch/5ch風議論の自動生成** — 複数のAIエージェントにそれぞれ異なるペルソナ（性格・口調・立場）を割り当て、掲示板風のリアルな議論を生成します。スレッドタブでリアルタイムに進行を確認できます。
- **まとめ記事の自動編集** — 議論ログからスレッドタイトルとまとめ記事をAIが自動生成し、ハイライト付きの見やすいレイアウトで表示します。
- **2つのチャットパターン** — `SelectorGroupChat`（LLMが次の発言者を動的に選択）と `RoundRobinGroupChat`（固定順で順番に発言）を選択でき、掲示板らしい自然な流れを実現します。
- **Web情報の自動取得** — 参考URLの本文取得と DuckDuckGo Web検索による補足情報の取り込みに対応しています。APIキー不要で検索を利用できます。
- **添付ファイル・画像の解析** — テキストファイルの取り込みに加え、添付画像をvision対応LLMで解析し、議論コンテキストに反映します。
- **多形式エクスポート** — スレッド・まとめ・生ログの3種類を `txt` / `json` / `html` の3形式（計9ファイル）で出力し、ZIPにまとめてダウンロードできます。
- **柔軟なLLM設定** — 議論用とまとめ用で別々のプロバイダー・モデルを選択可能です。OpenAI、Gemini、Ollama、OpenRouter、カスタムOpenAI互換APIに対応しています。
- **Ollama Thinking制御** — Ollama の thinking（推論）モードを議論用・まとめ用で個別にON/OFF切り替えできます。
- **プリセット・設定保存** — テーマプリセットの保存・復元、詳細設定のJSON保存に対応し、次回起動時に自動反映されます。
- **途中停止・進捗表示** — 生成の途中停止機能（ExternalTermination による穏当な停止）、進捗表示、残り時間見積もりに対応しています。
- **トークン節約機能** — Web検索取得量、URL本文長、会話履歴件数、Thinking ON/OFFなど、APIコストを細かくコントロールできます。

---

## 技術スタック

このプロジェクトは以下の技術・ライブラリを使用しています。

**言語・ランタイム**: Python 3.10以上

**フレームワーク・ライブラリ**: Gradio 6（Web UI）、AutoGen AgentChat / Core / Ext 0.4（マルチエージェントフレームワーク）、PyYAML（設定ファイル）、httpx（HTTP通信）、BeautifulSoup4（HTML解析）、ddgs（DuckDuckGo検索）

**パッケージ管理・ビルド**: uv（パッケージマネージャ）、Hatchling（ビルドバックエンド）

**開発ツール**: pytest / pytest-asyncio（テスト）

---

## 必要環境

- **macOS**（Apple Silicon を想定）
- **Python 3.10** 以上
- **uv**（パッケージマネージャ）
- **Ollama**（ローカルLLMを使う場合のみ、別途起動が必要）

---

## セットアップ

```bash
# 1. リポジトリをクローンして移動
git clone https://github.com/Shuichi346/matome-site-generator.git
cd matome-site-generator

# 2. 設定ファイルを作成し、APIキーを記入
cp config/settings.yaml.example config/settings.yaml
# config/settings.yaml を編集して使用するプロバイダーのAPIキーを設定してください

# 3. 依存パッケージをインストール
uv sync

# 4. アプリを起動
uv run matome-site-generator
```

起動後、ブラウザで [http://127.0.0.1:7860](http://127.0.0.1:7860) を開いてください。

---

## 基本的な使い方

1. 「**テーマ**」に議論させたい内容を入力します。
2. 必要なら「**方向性・補足情報**」を入力します。
3. 必要なら参考URL、検索キーワード、添付ファイル、画像を追加します。
4. 議論回数、参加人数、トーン、利用モデルを設定します。
5. 「**生成**」を押すと、スレッド、まとめ、ログが順に作られます。スレッドタブでリアルタイムに議論の進行を確認できます。
6. 完了まで進んだ場合はZIPをダウンロードできます。

補足として、スレッドタイトルはAIが自動生成します。画像を添付すると議論開始前にvision対応LLMが画像内容を解析して議論へ反映します。vision非対応モデルでは画像添付は使えません。「中止」ボタンは以後の新しい重い処理を始めない停止要求であり、中止時はスレッド表示が途中まで残りますが、状況によってはまとめやZIPが生成されないことがあります。

---

## 対応LLMプロバイダー

| プロバイダー | 用途 | 主な設定 |
|---|---|---|
| `openai` | OpenAI API | `api_keys.openai` |
| `gemini` | Gemini API（OpenAI互換エンドポイント経由） | `api_keys.gemini` |
| `ollama` | ローカルLLM（thinking制御対応） | `local_servers.ollama_base_url` |
| `openrouter` | OpenRouter 経由の各種モデル | `api_keys.openrouter`, `openrouter.base_url` |
| `custom_openai` | 任意の OpenAI 互換 API | `custom_openai.base_url`, `custom_openai.api_key` |

---

## 設定ファイル

`config/settings.yaml` にAPIキーや接続先を記述します。ひな形は [config/settings.yaml.example](config/settings.yaml.example) です。`settings.yaml` は `.gitignore` で除外されているため、APIキーがGitに含まれることはありません。

主なセクションとして、`api_keys` には `openai`、`gemini`、`openrouter` のAPIキーを設定します。`local_servers` には `ollama_base_url` を設定します。`ollama` セクションでは `discussion_think`（議論用のthinking設定）、`summarizer_think`（まとめ用のthinking設定）、`model_info`（Ollamaモデルの能力設定。画像を使う場合は `vision: true` が必要）を設定できます。`openrouter` では `base_url` を、`custom_openai` では `base_url`・`api_key`・`model_info` を設定できます。`defaults` セクションでは議論用・まとめ用モデル、待機時間、チャットパターンを指定します。`web_fetch` セクションではWeb検索・URL取得のデフォルト設定を行います。

`web_fetch` では次の3項目を設定できます。

```yaml
web_fetch:
  max_search_results: 3              # Web検索で取得する件数
  max_url_content_length: 2000       # 各URL本文の最大文字数
  search_content_mode: "snippet"     # "snippet"=スニペット中心 / "full"=検索結果本文も取得
```

テーマ欄、補足欄、参考URL欄に手入力したURLは常に本文を取得します。`search_content_mode` は DuckDuckGo の検索結果にだけ適用されます。

---

## 議論パートのチャットパターン

議論パートでのエージェント発言順の決め方を2つのパターンから選択できます。

**SelectorGroupChat（デフォルト）** — まとめ用LLMが文脈を読んで次の発言者を動的に選択します。掲示板らしい自然な会話の流れが実現できます。同じエージェントの連続発言も許可されており、連投が自然な掲示板の雰囲気を再現します。セレクターにはまとめ用プロバイダー・モデルが使用されるため、追加のAPIコストが発生します。

**RoundRobinGroupChat** — 全エージェントが固定順で順番に発言します。安定した動作でAPIコストを抑えられます。

設定は詳細設定タブの「議論パートのチャットパターン」ドロップダウン、または `config/settings.yaml` の `defaults.chat_pattern` で変更できます。

```yaml
defaults:
  chat_pattern: "selector"   # "selector" または "round_robin"
```

---

## Ollama Thinking（推論）モード

Qwen3やDeepSeek-R1などのthinking対応モデルでは、Ollamaの `think` パラメータで推論モードを制御できます。設定方法は2つあります。

### UIから設定（推奨）

詳細設定タブの「Ollama Thinking設定」で、議論用・まとめ用それぞれに設定できます。「**ON**」でthinkingを有効化（精度が向上するが応答が遅くなる）、「**OFF**」でthinkingを無効化（高速応答）、「**モデルのデフォルト**」でモデル側の既定動作に従います。UI設定が `settings.yaml` より優先されます。

### settings.yaml から設定

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

画像添付を使う場合は、議論用モデルがvision対応である必要があります。`ollama` と `custom_openai` は `model_info.vision` で判定します。

推奨設定として、議論用は **OFF**（各レスの生成速度を重視）、まとめ用は **ON** または **OFF**（まとめ品質を重視するならON）です。

---

## トークン節約のための設定

LLM APIのトークン消費を抑えるための設定が複数用意されています。

**Web検索の取得量を減らす** — 詳細設定タブの「Web検索・URL取得設定」で、Web検索の取得件数を少なくする、URL本文の最大文字数を小さくする、検索結果の取得モードを `snippet`（タイトルとスニペット中心で軽量）にするといった調整ができます。手入力した参考URLは `snippet` モードでも常に本文を取得します。通常は `snippet` が推奨です。

**会話履歴を制限する** — 詳細設定タブの「エージェントに渡す会話履歴の最大件数」で、各エージェントが参照する履歴数を制限できます。`0` で制限なし、`10` 前後が省トークンと文脈維持のバランスが取りやすい設定です。最初のタスクメッセージは常に保持しつつ、直近の会話を優先して渡します。

**Ollama Thinking を OFF にする** — thinking（推論）モードが ON だとモデルが内部で長く考えるため、トークンを多く消費します。議論用は OFF にするのが効率的です。

**Web取得結果の設計上の工夫** — 補足のWeb取得結果は、議論のシステムプロンプトには直接入れず、実際の議論タスク側で参照する設計になっています。これにより、各エージェントの固定プロンプト肥大化を抑えています。

---

## 詳細設定タブでできること

詳細設定タブでは、議論用LLMとまとめ用LLMの個別設定、APIウェイトタイムの調整、議論パートのチャットパターン選択、Ollama Thinking の ON/OFF（議論用・まとめ用個別）、Ollama / OpenRouter / カスタムOpenAI互換の接続先指定、Web検索件数・URL本文長・検索モードの調整、会話履歴の最大件数の調整、および現在の設定の保存を行えます。

保存先は、UI設定が `config/ui_settings.json`、テーマプリセットが `config/presets.json` です。プロバイダーを切り替えると、前回そのプロバイダーで使ったモデル名が自動で復元されます。

---

## OpenRouter の使い方

1. [OpenRouter](https://openrouter.ai/) でAPIキーを取得します。
2. `config/settings.yaml` の `api_keys.openrouter` にキーを設定します。
3. 必要なら `openrouter.base_url` も設定します。
4. UIで `openrouter` を選び、モデル名に `openai/gpt-5-mini` のような形式を入力します。

---

## カスタムOpenAI互換プロバイダーの使い方

Together AI、Groq、Fireworks、自社プロキシなど、OpenAI互換APIを提供するサービスに接続できます。

1. `config/settings.yaml` の `custom_openai.base_url` を設定します。
2. 必要なら `custom_openai.api_key` を設定します。
3. UIで `custom_openai` を選び、モデル名を入力します。

UI上で入力したベースURLとAPIキーは、`settings.yaml` の値より優先されます。

---

## 出力ファイル

生成完了後、以下の3種類がそれぞれ `txt` / `json` / `html` で保存されます。

- **スレッド** — 2ch/5ch風の全レス表示
- **まとめ** — ハイライト付きのまとめサイト風記事
- **生ログ** — エージェント名とレス内容の生データ

通常完了時は合計9ファイルをZIPにまとめてダウンロードできます。中止した場合は、途中成果のみ表示されてZIPが作られないことがあります。出力先ディレクトリは `output/` です。

---

## テスト

テストは pytest / pytest-asyncio で実行できます。

```bash
# テストの実行
uv run pytest

# 詳細表示付きで実行
uv run pytest -v

# 特定のテストファイルを実行
uv run pytest tests/test_discussion.py -q
```

---

## プロジェクト構成

```
matome-site-generator/
├── pyproject.toml                  # プロジェクト定義・依存関係
├── config/
│   ├── settings.yaml.example       # 設定ファイルのテンプレート
│   └── presets.json                # テーマプリセット定義
├── src/
│   ├── app.py                      # Gradio UI・メインパイプライン
│   ├── agents/
│   │   ├── discussion.py           # 議論エージェント（GroupChat制御）
│   │   ├── summarizer.py           # まとめエージェント（JSON出力）
│   │   ├── persona.py              # ペルソナ生成・システムプロンプト
│   │   └── image_analyzer.py       # 添付画像のvision解析
│   ├── models/
│   │   └── client_factory.py       # LLMクライアント生成ファクトリー
│   ├── utils/
│   │   ├── rate_limiter.py         # APIリクエスト間ウェイト管理
│   │   └── web_fetcher.py          # URL取得・Web検索
│   └── formatter/
│       ├── html_renderer.py        # HTML生成（Gradio用・スタンドアロン用）
│       ├── text_exporter.py        # テキスト形式エクスポート
│       └── json_exporter.py        # JSON形式エクスポート
├── tests/                          # テストスイート
├── output/                         # 生成ファイル出力先
└── docs/
    └── DELETION_LOG.md             # コード削除・リファクタリング記録
```

---

## よくある調整

**レートリミットエラーが出る場合** — 「APIウェイトタイム」を3秒以上に増やしてください。

**生成コストを下げたい場合** — `snippet` モードを使用、Web検索の取得件数を3以下に設定、URL本文の最大文字数を2000前後に設定、会話履歴の最大件数を10前後に設定、Ollama Thinking を OFF にする、チャットパターンを `round_robin` にする（セレクターLLMの追加コストがなくなる）、といった調整が有効です。

**ローカルモデルを使いたい場合** — Ollamaサーバーを先に起動してください。

---

## ライセンス

このプロジェクトは [MIT License](LICENSE) の下で公開されています。