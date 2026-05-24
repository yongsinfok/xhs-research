import json
import time
from pathlib import Path
from urllib.parse import quote

import typer
from playwright.sync_api import sync_playwright
from rich.console import Console

from src.config import AppSettings, ensure_dirs
from src.scraper.parser import XiaohongshuScraper
from src.ai.client import AIClient
from src.ai.summarizer import Summarizer

app = typer.Typer(help="小红书 AI 调研工具 — 搜索帖子并生成 AI 汇总报告")
console = Console()

COOKIE_FILE = Path.home() / ".xhs-research" / "cookies.json"


def _ensure_logged_in(page, keyword: str) -> bool:
    """确保搜索页已登录并显示正确结果。返回 True 如果搜索结果已就绪。"""
    time.sleep(5)

    # 检查是否有正确搜索结果
    titles = page.evaluate("""() => {
        const cards = document.querySelectorAll('section.note-item');
        return Array.from(cards).slice(0, 5).map(c => {
            const t = c.querySelector('.title span, span.title');
            return t ? t.innerText.trim() : '';
        });
    }""")

    # 提取关键词片段用于匹配
    chunks = set()
    for i in range(0, len(keyword) - 1):
        chunks.add(keyword[i:i+2])

    text = ' '.join(titles)
    match_count = sum(1 for c in chunks if c in text)

    if match_count >= 2 and titles[0]:
        console.print("[green]✓ 搜索结果已加载[/green]")
        return True

    # 没有正确结果 → 需要登录
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


@app.command()
def search(
    keyword: str = typer.Argument(..., help="搜索关键词"),
    limit: int = typer.Option(20, "--limit", "-l", min=1, max=50, help="抓取帖子数量"),
    model: str | None = typer.Option(None, "--model", "-m", help="覆盖 AI 模型"),
    output: str | None = typer.Option(None, "--output", "-o", help="输出文件路径"),
    json_output: bool = typer.Option(False, "--json", help="同时输出 JSON"),
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

        # 保存 cookies（登录成功后）
        cookies = context.cookies()
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

        # 抓取
        scraper = XiaohongshuScraper(page, settings.scraper.comments_per_post)
        posts = scraper.search(keyword, limit)

        if not posts:
            console.print("[yellow]未抓到帖子。[/yellow]")
            raise typer.Exit(1)

        console.print(f"[green]✓ 抓取到 {len(posts)} 个帖子[/green]")
        if scraper.related_searches:
            console.print(f"[cyan]相关搜索: {', '.join(scraper.related_searches[:8])}[/cyan]")

        related_searches = scraper.related_searches

    finally:
        context.close()
        browser.close()
        p.stop()

    # AI 汇总
    console.print("[cyan]🤖 AI 生成报告中...[/cyan]")
    ai_client = AIClient(settings.ai)
    summarizer = Summarizer(ai_client)
    report = summarizer.generate_report(keyword, posts, related_searches)

    if output:
        out_path = Path(output)
    else:
        safe_name = keyword.replace(" ", "_").replace("/", "_")[:30]
        out_path = Path(settings.output.save_dir) / f"{safe_name}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    console.print(f"[bold green]✅ 报告已保存: {out_path}[/bold green]")

    if json_output:
        json_path = out_path.with_suffix(".json")
        posts_data = [p.model_dump() for p in posts]
        json_path.write_text(json.dumps(posts_data, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]✅ JSON 数据: {json_path}[/green]")


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
