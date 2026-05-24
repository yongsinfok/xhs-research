# xhs-research

Search [Xiaohongshu (小红书)](https://www.xiaohongshu.com) and generate AI-powered research reports from the command line.

Instead of scrolling through dozens of posts one by one, type one command and get a structured summary with recommendations, price comparisons, and user sentiment — all powered by AI.

## Features

- **One command, full report** — search a keyword → scrape posts → AI generates a structured Markdown report
- **Multi-model support** — OpenAI, Claude, DeepSeek, or run locally with llama.cpp / Ollama (zero cost)
- **Smart summarization** — chunks large result sets and merges summaries to fit any model's context window
- **Structured output** — recommendations table, buying advice, red flags, sentiment breakdown
- **Login state persistence** — scan QR code once, cookies saved for reuse

## Quick Start

### 1. Install

```bash
git clone https://github.com/yongsinfok/xhs-research.git
cd xhs-research
pip install -r requirements.txt
playwright install firefox
```

### 2. Configure AI model

```bash
mkdir -p ~/.xhs-research
cp config.example.yaml ~/.xhs-research/config.yaml
```

Edit `~/.xhs-research/config.yaml`:

```yaml
ai:
  api_key: sk-your-key        # not needed for local models
  base_url: null              # local models: http://localhost:11434/v1
  model: gpt-4o               # or deepseek-chat, llama3, etc.
```

### 3. Run

```bash
PYTHONPATH=. PYTHONIOENCODING=utf-8 python -m src.cli search "马来西亚高性价比扫地机器人"
```

A browser window opens. Scan the QR code with the Xiaohongshu app to log in (only needed the first time). The tool then scrapes posts and generates a report.

## Usage

```bash
# Basic search (default 20 posts)
python -m src.cli search "吉隆坡美食推荐"

# More posts for better coverage
python -m src.cli search "新加坡PR申请攻略" --limit 30

# Use a specific model
python -m src.cli search " MacBook Pro M4 值得买吗" --model deepseek-chat

# Save to a specific path
python -m src.cli search "装修避坑指南" --output ./my-report.md

# Also export raw data as JSON
python -m src.cli search "搬家攻略" --json

# View config file location
python -m src.cli config-path
```

## Report Example

```markdown
# 马来西亚扫地机器人推荐 调研报告

> 基于 20 篇小红书帖子 · 2026-05-25

## 核心发现

- 小米 X20+ 关注度最高（447赞），有实测背书
- Dreame D20/Ultra 为热门候选，性价比讨论多
- Mova E40 作为竞品出现

## 推荐清单

| 品牌/型号   | 提及次数 | 最高赞 | 定位       |
|-------------|---------|--------|------------|
| 小米 X20+   | 1+      | 447    | 高关注实测 |
| Dreame D20 Ultra | 2  | 131   | 热门候选   |
| Dreame D20  | 1       | 28     | 性价比讨论 |
| Mova E40    | 1       | 28     | 竞品对比   |

## 购买建议 / 踩坑提醒 / 观点分布
...
```

## Supported AI Models

| Provider   | `base_url`                          | `model` example    | Cost     |
|------------|--------------------------------------|--------------------|----------|
| OpenAI     | _(default)_                          | `gpt-4o`           | Paid     |
| Anthropic  | _(default)_                          | `claude-sonnet-4-6` | Paid    |
| DeepSeek   | `https://api.deepseek.com/v1`       | `deepseek-chat`    | Low cost |
| Ollama     | `http://localhost:11434/v1`          | `llama3`, `qwen2`  | Free     |
| llama.cpp  | `http://localhost:8080/v1`           | _(local model)_    | Free     |
| Any OpenAI-compatible API | _(your endpoint)_        | _(your model)_     | Varies   |

Any endpoint that exposes an OpenAI-compatible `/v1/chat/completions` API works out of the box.

## Project Structure

```
xhs-research/
├── src/
│   ├── cli.py              # CLI entry point (typer)
│   ├── config.py           # YAML config loader
│   ├── models/post.py      # Post / Comment data models
│   ├── ai/
│   │   ├── client.py       # Unified AI client (OpenAI SDK)
│   │   └── summarizer.py   # Chunk + merge summarization
│   └── scraper/
│       ├── browser.py      # Playwright browser manager
│       ├── login.py        # QR code login handler
│       └── parser.py       # Search result scraper
├── config.example.yaml
├── requirements.txt
└── README.md
```

## Limitations

- **Xiaohongshu web restrictions** — post detail pages are often blocked on web, so reports are primarily based on search result titles and card summaries. Increasing `--limit` improves coverage.
- **Anti-scraping** — uses standard Playwright Firefox. For better evasion, consider [camoufox](https://github.com/daijro/camoufox).
- **Login expiration** — cookies may expire; re-scan QR code when prompted.
- **Personal use only** — respect Xiaohongshu's terms of service. Do not use for commercial scraping.

## Contributing

Issues and pull requests are welcome. Areas to contribute:

- Mobile API support for full post content
- Better anti-detection (camoufox integration)
- Web UI or API server mode
- Support for other platforms (Douyin, Bilibili, etc.)

## License

MIT
