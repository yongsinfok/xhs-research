import json
import time
from pathlib import Path
from urllib.parse import quote

import typer
from playwright.sync_api import sync_playwright
from rich.console import Console
from rich.table import Table

from xhs_research.config import AppSettings, ensure_dirs
from xhs_research.scraper.parser import XiaohongshuScraper
from xhs_research.scraper.api_engine import APIEngine
from xhs_research.ai.client import AIClient
from xhs_research.ai.summarizer import Summarizer

app = typer.Typer(help="小红书 AI 调研工具 — 搜索帖子并生成 AI 汇总报告")
console = Console()

COOKIE_FILE = Path.home() / ".xhs-research" / "cookies.json"


def _ensure_logged_in(page, keyword: str) -> bool:
    """确保搜索页已登录并显示正确结果。返回 True 如果搜索结果已就绪。"""
    time.sleep(5)

    titles = page.evaluate("""() => {
        const cards = document.querySelectorAll('section.note-item');
        return Array.from(cards).slice(0, 5).map(c => {
            const t = c.querySelector('.title span, span.title');
            return t ? t.innerText.trim() : '';
        });
    }""")

    chunks = set()
    for i in range(0, len(keyword) - 1):
        chunks.add(keyword[i:i+2])

    text = ' '.join(titles)
    match_count = sum(1 for c in chunks if c in text)

    if match_count >= 2 and titles[0]:
        console.print("[green]✓ 搜索结果已加载[/green]")
        return True

    console.print("[yellow]请在浏览器中扫码登录小红书...[/yellow]")
    for i in range(120):
        time.sleep(1)
        titles = page.evaluate("""() => {
            const cards = document.querySelectorAll('section.note-item');
            return Array.from(cards).slice(0, 5).map(c => {
                const t = c.querySelector('.title span, span.title');
                return t ? t.innerText.trim() : '';
            });
        }""")
        text = ' '.join(titles)
        match_count = sum(1 for c in chunks if c in text)
        if match_count >= 2 and titles[0]:
            console.print(f"[green]✓ 登录成功！[/green]")
            return True
        if (i + 1) % 15 == 0:
            console.print(f"[yellow]等待中... {i+1}/120s[/yellow]")

    return False


def _run_browser_search(keyword: str, limit: int, settings: AppSettings) -> tuple[list, list[str]]:
    """Playwright browser engine (fallback)."""
    p = sync_playwright().start()
    browser = p.firefox.launch(headless=False)
    context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="zh-CN")

    if COOKIE_FILE.exists():
        cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        context.add_cookies(cookies)

    page = context.new_page()

    try:
        url = f"https://www.rednote.com/search_result?keyword={quote(keyword)}&source=web_search_result_notes&type=51"
        page.goto(url, wait_until="domcontentloaded")

        if not _ensure_logged_in(page, keyword):
            console.print("[red]❌ 登录超时[/red]")
            raise typer.Exit(1)

        cookies = context.cookies()
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

        scraper = XiaohongshuScraper(page, settings.scraper.comments_per_post)
        posts = scraper.search(keyword, limit)
        return posts, scraper.related_searches

    finally:
        context.close()
        browser.close()
        p.stop()


def _run_api_search(keyword: str, limit: int, settings: AppSettings) -> tuple[list, list[str]]:
    """API engine with signing browser."""
    engine = APIEngine(settings.scraper.comments_per_post)
    engine.start()

    try:
        if not engine.wait_for_login():
            console.print("[red]❌ 登录超时[/red]")
            raise typer.Exit(1)

        posts = engine.search(keyword, limit)
        return posts, []
    finally:
        engine.close()


def _save_report(report: str, keyword: str, output: str | None, settings: AppSettings) -> Path:
    if output:
        out_path = Path(output)
        # If output is a directory, auto-generate filename
        if out_path.is_dir() or out_path.suffix not in (".md", ".txt", ".markdown"):
            safe_name = keyword.replace(" ", "_").replace("/", "_")[:30]
            out_path = out_path / f"{safe_name}.md"
    else:
        safe_name = keyword.replace(" ", "_").replace("/", "_")[:30]
        out_path = Path(settings.output.save_dir) / f"{safe_name}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    return out_path


@app.command()
def search(
    keyword: str = typer.Argument(..., help="搜索关键词"),
    limit: int = typer.Option(20, "--limit", "-l", min=1, max=50, help="抓取帖子数量"),
    model: str | None = typer.Option(None, "--model", "-m", help="覆盖 AI 模型"),
    output: str | None = typer.Option(None, "--output", "-o", help="输出文件路径"),
    json_output: bool = typer.Option(False, "--json", help="同时输出 JSON"),
    engine: str = typer.Option("api", "--engine", "-e", help="搜索引擎: api | browser"),
) -> None:
    """搜索小红书并生成 AI 调研报告。"""
    settings = AppSettings.load()
    ensure_dirs(settings)

    if model:
        settings.ai.model = model

    if not settings.ai.api_key and not settings.ai.base_url:
        console.print("[red]错误: 请在 config.yaml 中配置 api_key 或 base_url[/red]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]🔍 小红书调研: {keyword}[/bold cyan]")
    console.print(f"[dim]引擎: {engine}[/dim]")

    if engine == "api":
        posts, related_searches = _run_api_search(keyword, limit, settings)
    else:
        posts, related_searches = _run_browser_search(keyword, limit, settings)

    if not posts:
        console.print("[yellow]未抓到帖子。[/yellow]")
        raise typer.Exit(1)

    console.print(f"[green]✓ 抓取到 {len(posts)} 个帖子[/green]")

    # AI 汇总
    console.print("[cyan]🤖 AI 生成报告中...[/cyan]")
    ai_client = AIClient(settings.ai)
    summarizer = Summarizer(ai_client)
    report = summarizer.generate_report(keyword, posts, related_searches)

    out_path = _save_report(report, keyword, output, settings)
    console.print(f"[bold green]✅ 报告已保存: {out_path}[/bold green]")

    if json_output:
        json_path = out_path.with_suffix(".json")
        posts_data = [p.model_dump() for p in posts]
        json_path.write_text(json.dumps(posts_data, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]✅ JSON 数据: {json_path}[/green]")


@app.command()
def compare(
    topic_a: str = typer.Argument(..., help="第一个搜索词"),
    topic_b: str = typer.Argument(..., help="第二个搜索词"),
    limit: int = typer.Option(15, "--limit", "-l", min=5, max=50, help="每个话题抓取帖子数量"),
    model: str | None = typer.Option(None, "--model", "-m", help="覆盖 AI 模型"),
    output: str | None = typer.Option(None, "--output", "-o", help="输出文件路径"),
    engine: str = typer.Option("api", "--engine", "-e", help="搜索引擎: api | browser"),
) -> None:
    """对比两个话题，生成 AI 对比报告。"""
    settings = AppSettings.load()
    ensure_dirs(settings)

    if model:
        settings.ai.model = model

    if not settings.ai.api_key and not settings.ai.base_url:
        console.print("[red]错误: 请在 config.yaml 中配置 api_key 或 base_url[/red]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]🔍 小红书对比: {topic_a} vs {topic_b}[/bold cyan]")

    # Search A
    console.print(f"\n[bold]━━━ 搜索 A: {topic_a} ━━━[/bold]")
    if engine == "api":
        posts_a, related_a = _run_api_search(topic_a, limit, settings)
    else:
        posts_a, related_a = _run_browser_search(topic_a, limit, settings)

    # Search B
    console.print(f"\n[bold]━━━ 搜索 B: {topic_b} ━━━[/bold]")
    if engine == "api":
        posts_b, related_b = _run_api_search(topic_b, limit, settings)
    else:
        posts_b, related_b = _run_browser_search(topic_b, limit, settings)

    if not posts_a and not posts_b:
        console.print("[red]两个话题都未抓到帖子。[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ A: {len(posts_a)} 帖子, B: {len(posts_b)} 帖子[/green]")

    # AI 对比
    console.print("[cyan]🤖 AI 生成对比报告...[/cyan]")
    ai_client = AIClient(settings.ai)
    report = _generate_compare_report(ai_client, topic_a, topic_b, posts_a, posts_b)

    keyword = f"{topic_a}_vs_{topic_b}"
    out_path = _save_report(report, keyword, output, settings)
    console.print(f"[bold green]✅ 对比报告已保存: {out_path}[/bold green]")


def _generate_compare_report(
    client: AIClient,
    topic_a: str,
    topic_b: str,
    posts_a: list,
    posts_b: list,
) -> str:
    """Generate a comparison report using AI."""
    from xhs_research.ai.summarizer import _posts_to_text
    from datetime import date

    system_prompt = """你是一个专业的消费决策对比分析助手。用户会给你两组来自小红书的帖子数据，分别对应两个不同的搜索话题。

请生成一份详细的对比报告，包含以下结构：

1. **概览对比表** — 用表格对比两个话题的关键指标（讨论热度、价格、口碑等）
2. **各自亮点** — 分别总结 A 和 B 的主要优点/推荐点
3. **各自不足** — 分别总结 A 和 B 的缺点/踩坑点
4. **价格对比** — 如果涉及产品/服务，对比价格区间
5. **适合谁** — 分析哪种人群适合选 A，哪种适合选 B
6. **综合建议** — 给出最终推荐和决策参考

输出格式：中文 Markdown。尽量具体、有数据支撑。"""

    user_content = f"""## 话题 A: {topic_a}
帖子数量: {len(posts_a)}

{_posts_to_text(posts_a[:15])}

---

## 话题 B: {topic_b}
帖子数量: {len(posts_b)}

{_posts_to_text(posts_b[:15])}"""

    resp = client.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ])

    return f"# {topic_a} vs {topic_b} 对比报告\n\n> 基于 {len(posts_a)} + {len(posts_b)} 篇小红书帖子 · {date.today()}\n\n{resp}"


@app.command()
def config_path() -> None:
    """显示配置文件路径。"""
    path = Path.home() / ".xhs-research" / "config.yaml"
    console.print(f"配置文件: {path}")
    if path.exists():
        console.print(path.read_text(encoding="utf-8"))
    else:
        console.print("[yellow]配置文件不存在，将使用默认配置。[/yellow]")


if __name__ == "__main__":
    app()
