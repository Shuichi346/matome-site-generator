<table>
  <thead>
    <tr>
      <th style="text-align:center"><a href="README_en.md">English</a></th>
      <th style="text-align:center"><a href="README.md">日本語</a></th>
    </tr>
  </thead>
</table>

<p align="center">
  <strong>2ch/5ch Summary-style Generator</strong>
</p>

<p align="center">
  A web app where multiple AI agents discuss in an anonymous bulletin board style and automatically generate "summary site-style" articles
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Gradio-6.x-orange?logo=gradio" alt="Gradio 6">
  <img src="https://img.shields.io/badge/AutoGen-0.4.x-green" alt="AutoGen 0.4">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="MIT License">
  <img src="https://img.shields.io/badge/platform-macOS%20(Apple%20Silicon)-lightgrey?logo=apple" alt="macOS">
</p>

---

## Table of Contents

- [Overview](#overview)
- [Main Features](#main-features)
- [Technology Stack](#technology-stack)
- [Requirements](#requirements)
- [Setup](#setup)
- [Basic Usage](#basic-usage)
- [Supported LLM Providers](#supported-llm-providers)
- [Configuration File](#configuration-file)
- [Discussion Part Chat Patterns](#discussion-part-chat-patterns)
- [Ollama Thinking (Inference) Mode](#ollama-thinking-inference-mode)
- [Settings for Token Conservation](#settings-for-token-conservation)
- [Advanced Settings Tab Features](#advanced-settings-tab-features)
- [How to Use OpenRouter](#how-to-use-openrouter)
- [How to Use Custom OpenAI-Compatible Providers](#how-to-use-custom-openai-compatible-providers)
- [Output Files](#output-files)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Common Adjustments](#common-adjustments)
- [License](#license)

---

## Overview

**matome-site-generator** is a web application that facilitates discussions among multiple AI agents in the style of 2channel/5channel anonymous bulletin boards based on input themes, and automatically formats these discussion logs into "summary site-style" articles.

It can use different LLM models for the discussion and summary parts, and includes a wide range of practical features such as URL referencing, DuckDuckGo web search, analysis of attached files and images, theme preset saving, mid-process stopping, and ZIP batch downloads.

In the discussion part, you can switch between two chat patterns: `SelectorGroupChat` (where the LLM dynamically selects the next speaker based on context) and `RoundRobinGroupChat` (where speakers take turns in a fixed order).

---

## Main Features

- **Automatic generation of 2ch/5ch-style discussions** — Multiple AI agents are assigned different personas (personality, tone, stance) to generate realistic bulletin board-style discussions. You can monitor progress in real-time on the thread tab.
- **Automatic summary article editing** — AI automatically generates thread titles and summary articles from discussion logs, displayed in an easy-to-read layout with highlights.
- **Two chat patterns** — Choose between `SelectorGroupChat` (LLM dynamically selects next speaker) and `RoundRobinGroupChat` (fixed order turns), achieving natural bulletin board-like flow.
- **Automatic web information retrieval** — Supports reference URL content extraction and supplementary information gathering through DuckDuckGo web search. Search can be used without API keys.
- **Attached file and image analysis** — In addition to text file import, attached images are analyzed by vision-capable LLMs and reflected in the discussion context.
- **Multi-format export** — Outputs three types (thread, summary, raw logs) in three formats each (txt/json/html, total 9 files) and packages them for ZIP download.
- **Flexible LLM settings** — Separate provider and model selection for discussion and summary parts. Supports OpenAI, Gemini, Ollama, OpenRouter, and custom OpenAI-compatible APIs.
- **Ollama Thinking control** — Individual ON/OFF switching of Ollama's thinking (inference) mode for discussion and summary parts.
- **Preset and settings saving** — Supports theme preset saving/restoration and detailed settings JSON saving, automatically applied on next startup.
- **Mid-process stopping and progress display** — Supports mid-generation stopping (graceful termination via ExternalTermination), progress display, and remaining time estimation.
- **Token conservation features** — Fine control over API costs through web search retrieval volume, URL content length, conversation history count, Thinking ON/OFF, and more.

---

## Technology Stack

This project uses the following technologies and libraries.

**Language & Runtime**: Python 3.10+

**Frameworks & Libraries**: Gradio 6 (Web UI), AutoGen AgentChat / Core / Ext 0.4 (Multi-agent framework), PyYAML (Configuration files), httpx (HTTP communication), BeautifulSoup4 (HTML parsing), ddgs (DuckDuckGo search)

**Package Management & Build**: uv (Package manager), Hatchling (Build backend)

**Development Tools**: pytest / pytest-asyncio (Testing)

---

## Requirements

- **macOS** (Assumes Apple Silicon)
- **Python 3.10** or higher
- **uv** (Package manager)
- **Ollama** (Only required if using local LLMs, must be started separately)

---

## Setup

```bash
# 1. Clone the repository and navigate
git clone https://github.com/Shuichi346/matome-site-generator.git
cd matome-site-generator

# 2. Create configuration file and enter API keys
cp config/settings.yaml.example config/settings.yaml
# Edit config/settings.yaml to set API keys for the providers you'll use

# 3. Install dependencies
uv sync

# 4. Start the application
uv run matome-site-generator
```

After startup, open [http://127.0.0.1:7860](http://127.0.0.1:7860) in your browser.

---

## Basic Usage

1. Enter the topic you want discussed in "**Theme**".
2. If needed, enter "**Direction & Supplementary Information**".
3. If needed, add reference URLs, search keywords, attached files, or images.
4. Set discussion rounds, participants, tone, and models to use.
5. Click "**Generate**" to create thread, summary, and logs in sequence. You can monitor discussion progress in real-time on the thread tab.
6. When complete, you can download the ZIP file.

Note: Thread titles are automatically generated by AI. When images are attached, vision-capable LLMs analyze image content before discussion begins and reflect it in the discussion. Image attachment cannot be used with non-vision models. The "Stop" button requests termination of subsequent heavy processes; when stopped, thread display remains partial, but summary and ZIP may not be generated depending on circumstances.

---

## Supported LLM Providers

| Provider | Use Case | Main Settings |
|---|---|---|
| `openai` | OpenAI API | `api_keys.openai` |
| `gemini` | Gemini API (via OpenAI-compatible endpoint) | `api_keys.gemini` |
| `ollama` | Local LLM (with thinking control support) | `local_servers.ollama_base_url` |
| `openrouter` | Various models via OpenRouter | `api_keys.openrouter`, `openrouter.base_url` |
| `custom_openai` | Any OpenAI-compatible API | `custom_openai.base_url`, `custom_openai.api_key` |

---

## Configuration File

API keys and connection endpoints are described in `config/settings.yaml`. The template is [config/settings.yaml.example](config/settings.yaml.example). `settings.yaml` is excluded by `.gitignore`, so API keys will not be included in Git.

Main sections include: `api_keys` for setting API keys for `openai`, `gemini`, and `openrouter`. `local_servers` for setting `ollama_base_url`. The `ollama` section allows setting `discussion_think` (thinking setting for discussions), `summarizer_think` (thinking setting for summaries), and `model_info` (Ollama model capability settings - `vision: true` is required for image use). `openrouter` allows setting `base_url`, and `custom_openai` allows setting `base_url`, `api_key`, and `model_info`. The `defaults` section specifies discussion/summary models, wait times, and chat patterns. The `web_fetch` section sets default settings for web search and URL retrieval.

The `web_fetch` section can configure the following three items:

```yaml
web_fetch:
  max_search_results: 3              # Number of items to retrieve from web search
  max_url_content_length: 2000       # Maximum characters for each URL content
  search_content_mode: "snippet"     # "snippet"=snippet-focused / "full"=also retrieve search result content
```

URLs manually entered in theme, supplement, and reference URL fields always retrieve content. `search_content_mode` applies only to DuckDuckGo search results.

---

## Discussion Part Chat Patterns

You can choose between two patterns for determining the order of agent statements in the discussion part.

**SelectorGroupChat (Default)** — The summary LLM reads context and dynamically selects the next speaker. This achieves natural conversation flow typical of bulletin boards. Consecutive statements by the same agent are allowed, reproducing the natural bulletin board atmosphere of consecutive posts. The selector uses the summary provider and model, incurring additional API costs.

**RoundRobinGroupChat** — All agents speak in turn in a fixed order. Provides stable operation with reduced API costs.

Settings can be changed via the "Discussion Part Chat Pattern" dropdown in the Advanced Settings tab, or `defaults.chat_pattern` in `config/settings.yaml`.

```yaml
defaults:
  chat_pattern: "selector"   # "selector" or "round_robin"
```

---

## Ollama Thinking (Inference) Mode

For thinking-capable models like Qwen3 and DeepSeek-R1, you can control inference mode with Ollama's `think` parameter. There are two ways to configure this.

### UI Configuration (Recommended)

In the Advanced Settings tab's "Ollama Thinking Settings", you can configure discussion and summary parts separately. "**ON**" enables thinking (improves accuracy but slower response), "**OFF**" disables thinking (fast response), "**Model Default**" follows the model's default behavior. UI settings take precedence over `settings.yaml`.

### Configuration via settings.yaml

```yaml
ollama:
  discussion_think: false    # For discussion
  summarizer_think: true     # For summary
  model_info:
    vision: false
    function_calling: false
    json_output: true
    structured_output: false
```

When using image attachments, the discussion model must be vision-capable. `ollama` and `custom_openai` are determined by `model_info.vision`.

Recommended settings: Discussion part **OFF** (prioritize response speed for each post), Summary part **ON** or **OFF** (ON if prioritizing summary quality).

---

## Settings for Token Conservation

Multiple settings are available to reduce LLM API token consumption.

**Reduce web search retrieval volume** — In the Advanced Settings tab's "Web Search & URL Retrieval Settings", you can reduce web search retrieval count, decrease URL content maximum character count, and set search result retrieval mode to `snippet` (lightweight, focused on titles and snippets). Manually entered reference URLs always retrieve content even in `snippet` mode. `snippet` is usually recommended.

**Limit conversation history** — In the Advanced Settings tab's "Maximum conversation history items passed to agents", you can limit the number of history items each agent references. `0` for no limit, around `10` provides good balance between token saving and context preservation. The initial task message is always retained while prioritizing recent conversations.

**Turn OFF Ollama Thinking** — When thinking (inference) mode is ON, models consume more tokens by thinking internally for longer periods. Setting discussion part to OFF is efficient.

**Web retrieval result design considerations** — Supplementary web retrieval results are not directly included in discussion system prompts but referenced on the actual discussion task side. This prevents bloating of each agent's fixed prompts.

---

## Advanced Settings Tab Features

The Advanced Settings tab allows: individual settings for discussion and summary LLMs, API wait time adjustment, discussion part chat pattern selection, Ollama Thinking ON/OFF (individual for discussion/summary), connection endpoint specification for Ollama/OpenRouter/custom OpenAI-compatible, adjustment of web search count/URL content length/search mode, conversation history maximum count adjustment, and saving current settings.

Save locations are: UI settings to `config/ui_settings.json`, theme presets to `config/presets.json`. When switching providers, the last model name used with that provider is automatically restored.

---

## How to Use OpenRouter

1. Obtain an API key from [OpenRouter](https://openrouter.ai/).
2. Set the key in `config/settings.yaml` under `api_keys.openrouter`.
3. If needed, also set `openrouter.base_url`.
4. Select `openrouter` in the UI and enter model names in format like `openai/gpt-5-mini`.

---

## How to Use Custom OpenAI-Compatible Providers

You can connect to services providing OpenAI-compatible APIs such as Together AI, Groq, Fireworks, or your own proxy.

1. Set `custom_openai.base_url` in `config/settings.yaml`.
2. If needed, set `custom_openai.api_key`.
3. Select `custom_openai` in the UI and enter the model name.

Base URL and API key entered in the UI take precedence over `settings.yaml` values.

---

## Output Files

After generation completion, the following three types are saved in `txt` / `json` / `html` formats each.

- **Thread** — Full post display in 2ch/5ch style
- **Summary** — Summary site-style article with highlights
- **Raw Log** — Raw data of agent names and post content

Upon normal completion, all 9 files are packaged into a ZIP for download. When stopped mid-process, only partial results may be displayed without ZIP creation. Output directory is `output/`.

---

## Testing

Tests can be run with pytest / pytest-asyncio.

```bash
# Run tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_discussion.py -q
```

---

## Project Structure

```
matome-site-generator/
├── pyproject.toml                  # Project definition & dependencies
├── config/
│   ├── settings.yaml.example       # Configuration file template
│   └── presets.json                # Theme preset definitions
├── src/
│   ├── app.py                      # Gradio UI & main pipeline
│   ├── agents/
│   │   ├── discussion.py           # Discussion agents (GroupChat control)
│   │   ├── summarizer.py           # Summary agent (JSON output)
│   │   ├── persona.py              # Persona generation & system prompts
│   │   └── image_analyzer.py       # Vision analysis of attached images
│   ├── models/
│   │   └── client_factory.py       # LLM client generation factory
│   ├── utils/
│   │   ├── rate_limiter.py         # API request interval wait management
│   │   └── web_fetcher.py          # URL retrieval & web search
│   └── formatter/
│       ├── html_renderer.py        # HTML generation (for Gradio & standalone)
│       ├── text_exporter.py        # Text format export
│       └── json_exporter.py        # JSON format export
├── tests/                          # Test suite
├── output/                         # Generated file output destination
└── docs/
    └── DELETION_LOG.md             # Code deletion & refactoring log
```

---

## Common Adjustments

**For rate limit errors** — Increase "API Wait Time" to 3 seconds or more.

**To reduce generation costs** — Use `snippet` mode, set web search retrieval count to 3 or less, set URL content maximum characters to around 2000, set conversation history maximum count to around 10, turn Ollama Thinking OFF, set chat pattern to `round_robin` (eliminates additional selector LLM costs).

**To use local models** — Start the Ollama server first.

---

## License

This project is released under the [MIT License](LICENSE).