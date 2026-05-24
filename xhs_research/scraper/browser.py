import json
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page


class BrowserManager:
    """使用持久化 user_data_dir 保存登录态，避免每次重新登录。"""

    def __init__(self, profile_dir: str):
        self.profile_dir = Path(profile_dir)
        self._playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None

    def start(self) -> Page:
        self._playwright = sync_playwright().start()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        # user_data_dir 会自动保存 cookies、localStorage 等
        self.context = self._playwright.firefox.launch_persistent_context(
            str(self.profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        return self.context.new_page()

    def close(self) -> None:
        if self.context:
            self.context.close()
        if self._playwright:
            self._playwright.stop()
