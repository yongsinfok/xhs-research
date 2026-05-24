import time
from playwright.sync_api import Page
from rich.console import Console

console = Console()


def wait_for_login(page: Page, profile_dir: str) -> None:
    """等待用户在浏览器中扫码登录。登录态由 persistent_context 自动保存。"""
    console.print("[yellow]请在浏览器中扫码登录小红书...[/yellow]")
    page.goto("https://www.rednote.com", wait_until="domcontentloaded")

    console.print("[yellow]等待登录完成（最长 120 秒）...[/yellow]")
    for i in range(120):
        time.sleep(1)
        if page.query_selector("#search-input") or page.query_selector(".user .avatar"):
            console.print("[green]✓ 登录成功！（登录态已自动保存）[/green]")
            return
        if (i + 1) % 15 == 0:
            console.print(f"[yellow]等待中... {i+1}/120s[/yellow]")

    raise TimeoutError("登录超时（120秒），请重试")
