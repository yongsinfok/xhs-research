# xhs-research 🔍

小红书 AI 调研工具 — 搜索小红书帖子，AI 自动生成结构化汇总报告。

## 安装

```bash
cd xhs-research
pip install -e ".[dev]"
playwright install firefox
```

## 配置

```bash
mkdir -p ~/.xhs-research
cp config.example.yaml ~/.xhs-research/config.yaml
# 编辑 config.yaml，填入 API key
```

## 使用

```bash
# 首次使用会弹出浏览器要求扫码登录
xhs-research "马来西亚高性价比扫地机器人"

# 指定参数
xhs-research "xxx" --limit 30 --model deepseek --output ./report.md --json
```

## 支持模型

| 模型 | base_url | 说明 |
|------|----------|------|
| OpenAI | (默认) | gpt-4o / gpt-4o-mini |
| Claude | (默认) | 通过 Anthropic SDK |
| DeepSeek | `https://api.deepseek.com/v1` | deepseek-chat |
| llama.cpp | `http://localhost:8080/v1` | 本地运行，零成本 |
| Ollama | `http://localhost:11434/v1` | 本地运行，零成本 |
