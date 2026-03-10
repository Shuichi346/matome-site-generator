# 2ch/5ch Summary-Style Generator

This is a web application that generates anonymous bulletin board-style discussions based on input themes using multiple AI agents, and automatically formats the flow into "summary site-style" articles.

You can use different models for the discussion part and summary part. It supports URL references, web searches, file attachments, image analysis, preset saving, mid-process stopping, and bulk ZIP downloads.

## Main Features

- Generate 2ch/5ch-style discussions with multiple AI agents
- Automatically generate thread titles and summary articles from discussion logs
- Incorporate supplementary information through reference URL retrieval and DuckDuckGo web searches
- Import attached text files
- Analyze attached images with vision-compatible LLMs and reflect them in discussion context
- Thread display, summary display, raw log display
- Output in 3 formats (`txt`/`json`/`html`) and save 9 files bundled in ZIP
- Save provider, model, wait time, search settings, and conversation history settings in detailed settings tab
- Individual ON/OFF control of Ollama thinking (inference) mode for discussion and summary
- Theme preset saving, mid-process stopping, progress display, time estimation

## Requirements

- macOS
- Python 3.10 or higher
- `uv`

Notes:

- Assumes Apple Silicon
- Ollama needs to be started separately when used

## Setup

```bash
# 1. Place repository
cd matome-site-generator

# 2. Create configuration file
cp config/settings.yaml.example config/settings.yaml

# 3. Install dependencies
uv sync

# 4. Launch application
uv run matome-site-generator
```

After startup, open [http://127.0.0.1:7860](http://127.0.0.1:7860) in your browser.

## Supported LLM Providers

| Provider | Purpose | Main Settings |
|---|---|---|
| `openai` | OpenAI API | `api_keys.openai` |
| `gemini` | Gemini API | `api_keys.gemini` |
| `ollama` | Local LLM (thinking control supported) | `local_servers.ollama_base_url` |
| `openrouter` | Various models via OpenRouter | `api_keys.openrouter`, `openrouter.base_url` |
| `custom_openai` | Any OpenAI-compatible API | `custom_openai.base_url`, `custom_openai.api_key` |

## Configuration File

Describe API keys and connection destinations in `config/settings.yaml`. The template is [config/settings.yaml.example](config/settings.yaml.example).

Main sections:

- `api_keys`
  - `openai`
  - `gemini`
  - `openrouter`
- `local_servers`
  - `ollama_base_url`
- `ollama`
  - `discussion_think` — Thinking settings for discussion (true/false/unspecified)
  - `summarizer_think` — Thinking settings for summary (true/false/unspecified)
  - `model_info` — Ollama model capability settings. Requires `vision: true` when using images
- `openrouter`
  - `base_url`
- `custom_openai`
  - `base_url`
  - `api_key`
  - `model_info`
- `defaults`
  - Discussion/summary models, wait time
- `web_fetch`
  - Web search/URL retrieval defaults

In `web_fetch`, you can configure these 3 items:

```yaml
web_fetch:
  max_search_results: 3
  max_url_content_length: 2000
  search_content_mode: "snippet"
```

Meanings:

- `max_search_results`: Number of results to retrieve from web search
- `max_url_content_length`: Maximum character count for each URL content
- `search_content_mode`: Web search result retrieval mode. `snippet` focuses on snippets, `full` also retrieves search result content

Notes:

- URLs manually entered in theme, supplement, and reference URL fields always retrieve content
- `search_content_mode` applies only to DuckDuckGo search results

## About Ollama Thinking (Inference) Mode

For thinking-compatible models like Qwen3 and DeepSeek-R1, you can control inference mode with Ollama's `think` parameter.

There are two configuration methods:

### 1. Configure from UI (Recommended)

In the "Ollama Thinking Settings" in the detailed settings tab, you can configure separately for discussion and summary.

- **ON**: Enable thinking (improves accuracy but slows response)
- **OFF**: Disable thinking (fast response)
- **Model Default**: Follow model's default behavior

### 2. Configure from settings.yaml

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

UI settings take priority over `settings.yaml`.

When using image attachments, the discussion model needs to be vision-compatible. `ollama` and `custom_openai` are determined by `model_info.vision`.

### Recommended Settings

- Discussion: **OFF** (prioritize generation speed for each response)
- Summary: **ON** or **OFF** (ON if prioritizing summary quality)

## Basic Usage

1. Enter the content you want to discuss in "Theme".
2. If needed, enter "Direction/Supplementary Information".
3. If needed, add reference URLs, search keywords, attached files, and images.
4. Set discussion rounds, participant count, tone, and models to use.
5. Press "Generate" to create threads, summaries, and logs in sequence.
6. When completed, you can download the ZIP file.

Notes:

- Thread titles are automatically generated by AI
- When images are attached, vision-compatible LLM analyzes image content before discussion starts and reflects it in the discussion
- Image attachment cannot be used with non-vision compatible models
- "Stop" is a stop request that prevents starting new heavy processes
- When stopped, thread display remains up to that point, but summaries and ZIP may not be generated depending on the situation
- Content in detailed settings tab can be saved

## Settings for Token Conservation

The latest version strengthens settings to reduce LLM API token consumption.

### 1. Reduce Web Search Retrieval Volume

Use "Web Search/URL Retrieval Settings" in the detailed settings tab.

- `Web Search Result Count`
  - Smaller values save more tokens
- `URL Content Max Character Count`
  - Smaller values reduce the amount imported from each URL
- `Search Result Retrieval Mode`
  - `snippet`: Web search results are lightweight, focusing on titles and snippets
  - `full`: Also retrieves web search result content

Manually entered reference URLs always retrieve content even in `snippet` mode.

Usually `snippet` is recommended.

### 2. Limit Conversation History

In "Maximum Conversation History Count Passed to Agents" in the detailed settings tab, you can limit the number of history items each agent references.

- `0`: No limit
- Around `10`: Balanced setting for token saving and context maintenance

This limit always retains the initial task message while prioritizing recent conversations.

### 3. Turn OFF Ollama Thinking

When thinking (inference) mode is ON, the model thinks internally for longer periods, consuming more tokens. It's efficient to turn OFF for discussion.

### 4. Don't Put Too Much Web Retrieval Results into System Prompts

Supplementary web retrieval results are designed to be referenced on the actual discussion task side rather than directly in the discussion system prompt. This prevents bloating of each agent's fixed prompts.

## What You Can Do in Detailed Settings Tab

- Configure discussion LLM and summary LLM separately
- Adjust API wait time
- Turn Ollama Thinking ON/OFF (individual for discussion/summary)
- Specify connection destinations for Ollama/OpenRouter/Custom OpenAI-compatible
- Adjust web search count, URL content length, search mode
- Adjust maximum conversation history count
- Save current settings

Save destinations:

- UI settings: `config/ui_settings.json`
- Theme presets: `config/presets.json`

## How to Use OpenRouter

1. Obtain an API key from [OpenRouter](https://openrouter.ai/).
2. Configure `api_keys.openrouter` in `config/settings.yaml`.
3. If needed, also configure `openrouter.base_url`.
4. Select `openrouter` in the UI and enter model names in formats like `openai/gpt-5-mini`.

## How to Use Custom OpenAI-Compatible Providers

You can connect to OpenAI-compatible APIs like Together AI, Groq, Fireworks, and corporate proxies.

1. Configure `custom_openai.base_url` in `config/settings.yaml`.
2. If needed, configure `custom_openai.api_key`.
3. Select `custom_openai` in the UI and enter the model name.

Base URLs and API keys entered in the UI take priority over `settings.yaml` values.

## Output Files

After generation completion, the following 3 types are saved in `txt`/`json`/`html` formats each.

- Thread
- Summary
- Raw log

Upon normal completion, a total of 9 files are bundled into a ZIP for download. When stopped midway, only intermediate results may be displayed and ZIP may not be created. The output destination directory is `output/`.

## Common Adjustments

- Rate limit errors occur
  - Increase `API Wait Time` to 3 seconds or more
- Want to reduce generation costs
  - Use `snippet` mode
  - Set `Web Search Result Count` to 3 or less
  - Set `URL Content Max Character Count` to around 2000
  - Set `Max Conversation History Count` to around 10
  - Turn Ollama Thinking OFF
- Want to use local models
  - Start Ollama server first

## License

See [LICENSE](LICENSE).
