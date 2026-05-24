import os
from pathlib import Path
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import yaml


class AISettings(BaseModel):
    provider: str = "openai"
    api_key: str = ""
    base_url: str | None = None
    model: str = "gpt-4o"


class ScraperSettings(BaseModel):
    default_limit: int = 20
    max_limit: int = 50
    comments_per_post: int = 20
    cookie_path: str = ""  # 运行时填充


class OutputSettings(BaseModel):
    format: str = "markdown"
    save_dir: str = ""  # 运行时填充


class AppSettings(BaseSettings):
    ai: AISettings = AISettings()
    scraper: ScraperSettings = ScraperSettings()
    output: OutputSettings = OutputSettings()

    @classmethod
    def load(cls, config_path: Path | None = None) -> "AppSettings":
        if config_path is None:
            config_path = Path.home() / ".xhs-research" / "config.yaml"

        if config_path.exists():
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            ai_raw = raw.get("ai", {})
            scraper_raw = raw.get("scraper", {})
            output_raw = raw.get("output", {})
            return cls(
                ai=AISettings(**ai_raw) if ai_raw else AISettings(),
                scraper=ScraperSettings(**scraper_raw) if scraper_raw else ScraperSettings(),
                output=OutputSettings(**output_raw) if output_raw else OutputSettings(),
            )

        return cls()


def ensure_dirs(settings: AppSettings) -> None:
    """确保运行时目录存在，填充默认路径。"""
    home = Path.home() / ".xhs-research"
    reports_dir = home / "reports"
    home.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    if not settings.scraper.cookie_path:
        settings.scraper.cookie_path = str(home / "cookies.json")
    if not settings.output.save_dir:
        settings.output.save_dir = str(reports_dir)
