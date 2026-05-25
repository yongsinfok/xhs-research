"""Hybrid API engine for v0.2.

Uses rednote.com (international XHS) as the base domain.
Captures API responses passively while scraping DOM as primary source.
Gets structured JSON from API when available, DOM fallback when not.
"""

import json
import time
import re
from urllib.parse import quote

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Response
from rich.console import Console

from xhs_research.models.post import Post, Comment

console = Console()

BASE_URL = "https://www.rednote.com"


class APIEngine:
    """Hybrid engine: passive API interception + DOM scraping on rednote.com."""

    def __init__(self, comments_per_post: int = 20):
        self.comments_per_post = comments_per_post
        self._playwright: sync_playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._api_items: dict[str, dict] = {}  # note_id -> API item data
        self._feed_data: dict[str, dict] = {}  # note_id -> feed item data

    def start(self) -> Page:
        """Launch browser. Returns page for QR login."""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=False)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        self._page = self._context.new_page()

        # Passive response listener
        self._page.on("response", self._handle_response)

        self._page.goto(BASE_URL, wait_until="domcontentloaded")
        time.sleep(2)
        return self._page

    def _handle_response(self, response: Response) -> None:
        """Passively capture API response data."""
        url = response.url
        if response.status != 200:
            return
        if "/api/sns/web/" not in url:
            return

        try:
            body = response.json()
        except Exception:
            return

        if not body or not body.get("data"):
            return

        # Capture search results
        if "search/notes" in url:
            for item in body.get("data", {}).get("items", []):
                note_id = item.get("note_card", {}).get("note_id", "")
                if note_id:
                    self._api_items[note_id] = item

        # Capture feed/detail data
        elif "feed" in url:
            for item in body.get("data", {}).get("items", []):
                note_id = item.get("note_card", {}).get("note_id", "")
                if note_id:
                    self._feed_data[note_id] = item

    def wait_for_login(self, timeout: int = 120) -> bool:
        """Wait for user to scan QR."""
        console.print("[yellow]请在浏览器中扫码登录小红书...[/yellow]")
        for i in range(timeout):
            time.sleep(1)
            cookies = self._context.cookies()
            if any(c["name"] == "web_session" for c in cookies):
                console.print("[green]✓ 登录成功！[/green]")
                return True
            if (i + 1) % 15 == 0:
                console.print(f"[yellow]等待登录... {i+1}/{timeout}s[/yellow]")
        return False

    def search(self, keyword: str, limit: int = 20) -> list[Post]:
        """Search: navigate to search page, capture API + scrape DOM."""
        console.print(f"[cyan]搜索: {keyword}[/cyan]")
        self._api_items = {}
        self._feed_data = {}

        url = (
            f"{BASE_URL}/search_result?"
            f"keyword={quote(keyword)}&source=web_search_result_notes&type=51"
        )
        self._page.goto(url, wait_until="domcontentloaded")
        time.sleep(5)

        # Wait for search results to load
        self._wait_for_results(keyword)

        posts: list[Post] = []
        seen_ids: set[str] = set()

        # Primary: try API captured data first
        if self._api_items:
            console.print(f"[cyan]API 捕获到 {len(self._api_items)} 条数据[/cyan]")

        # Scroll and collect from both DOM and API
        for _ in range(20):
            cards = self._page.evaluate("""() => {
                const items = document.querySelectorAll('section.note-item');
                return Array.from(items).map(c => {
                    const titleEl = c.querySelector('.title span, span.title');
                    const title = titleEl ? titleEl.innerText.trim() : '';
                    const likesEl = c.querySelector('.like-wrapper .count, span.likeCount');
                    const likesText = likesEl ? likesEl.innerText.trim() : '0';
                    const authorEl = c.querySelector('.author .name, .author-wrapper .name');
                    const author = authorEl ? authorEl.innerText.trim() : '';

                    let noteId = '';
                    const exploreLink = c.querySelector('a[href*=\"/explore/\"]');
                    if (exploreLink) {
                        const m = exploreLink.href.match(/\\/explore\\/([a-f0-9]+)/);
                        if (m) noteId = m[1];
                    }
                    if (!noteId) {
                        const coverLink = c.querySelector('a.cover.mask, a[href*=\"/search_result/\"]');
                        if (coverLink) {
                            const m = coverLink.href.match(/\\/(?:search_result|explore)\\/([a-f0-9]+)/);
                            if (m) noteId = m[1];
                        }
                    }

                    return {title, likesText, author, noteId, text: c.innerText.trim()};
                }).filter(c => c.noteId && c.title);
            }""")

            for c in cards:
                if len(posts) >= limit:
                    break
                if c["noteId"] in seen_ids:
                    continue
                seen_ids.add(c["noteId"])

                # Merge DOM data with API data if available
                api_item = self._api_items.get(c["noteId"])
                post = self._build_post(c, api_item)
                posts.append(post)
                source = "API+DOM" if api_item else "DOM"
                console.print(f"  [{source}] [{len(posts)}/{limit}] {post.title[:50]}...")

            if len(posts) >= limit:
                break

            self._page.evaluate("window.scrollBy(0, 2000)")
            time.sleep(1.5)

        console.print(f"[green]✓ 搜索到 {len(posts)} 个帖子[/green]")

        # Fetch details
        self._fetch_details(posts)

        return posts

    def _build_post(self, card: dict, api_item: dict | None) -> Post:
        """Build Post from DOM card data, enriched with API data if available."""
        note_id = card["noteId"]
        title = card["title"]
        author = card["author"]
        likes = self._parse_count(card["likesText"])

        content_parts = [f"标题: {title}"]
        if author:
            content_parts.append(f"作者: {author}")
        if likes:
            content_parts.append(f"点赞: {likes}")

        tags = []
        desc = ""

        if api_item:
            note_card = api_item.get("note_card", {})
            api_likes = note_card.get("interact_info", {}).get("liked_count", "0")
            api_author = note_card.get("user", {}).get("nickname", "")
            desc = note_card.get("desc", "")
            tags = [t.get("name", "") for t in note_card.get("tag_list", []) if t.get("name")]

            # Use API data as more authoritative
            if api_author:
                content_parts[1] = f"作者: {api_author}" if len(content_parts) > 1 else f"作者: {api_author}"
            api_likes_int = self._parse_count(str(api_likes))
            if api_likes_int > likes:
                likes = api_likes_int

            if tags:
                content_parts.append(f"标签: {', '.join(tags)}")
            if desc and desc != title:
                content_parts.append(f"摘要: {desc}")
        else:
            content_parts.append(f"原文摘要: {card['text']}")

        return Post(
            id=note_id,
            title=title,
            content="\n".join(content_parts),
            likes=likes,
            author=author,
            url=f"{BASE_URL}/explore/{note_id}",
            tags=tags,
        )

    def _wait_for_results(self, keyword: str) -> None:
        """Wait for search results to appear."""
        chunks = set()
        for i in range(0, len(keyword) - 1):
            chunks.add(keyword[i:i+2])

        for attempt in range(30):
            time.sleep(1)
            try:
                titles = self._page.evaluate("""() => {
                    const cards = document.querySelectorAll('section.note-item');
                    return Array.from(cards).slice(0, 3).map(c => {
                        const t = c.querySelector('.title span, span.title');
                        return t ? t.innerText.trim() : '';
                    });
                }""")
                if titles and titles[0]:
                    text = ' '.join(titles)
                    if sum(1 for c in chunks if c in text) >= 2:
                        return
            except Exception:
                pass

    def _fetch_details(self, posts: list[Post]) -> None:
        """Open detail pages to get full content + comments."""
        console.print("[cyan]获取帖子详情...[/cyan]")
        self._feed_data = {}
        success = 0

        for i, post in enumerate(posts):
            console.print(f"  详情 ({i+1}/{len(posts)}): {post.title[:30]}...")

            try:
                self._page.goto(
                    f"{BASE_URL}/explore/{post.id}",
                    wait_until="domcontentloaded",
                )
                time.sleep(2)

                enriched = False

                # Try feed API data first
                if post.id in self._feed_data:
                    self._enrich_post(post, self._feed_data[post.id])
                    enriched = True

                # DOM fallback
                if not enriched:
                    self._extract_detail_from_dom(post)
                    enriched = True

                if enriched:
                    success += 1

            except Exception:
                console.print(f"[yellow]  详情获取失败[/yellow]")

        console.print(f"[cyan]详情获取: {success}/{len(posts)} 成功[/cyan]")

    def _enrich_post(self, post: Post, item: dict) -> None:
        """Enrich post with data from feed API response."""
        note_card = item.get("note_card", {})
        desc = note_card.get("desc", "")
        if desc and desc != post.title:
            post.content += f"\n\n详情正文:\n{desc}"

        comments_data = item.get("comments", [])
        if not comments_data:
            comments_data = note_card.get("comments", [])
        if comments_data:
            post.comments = [
                Comment(
                    author=c.get("user_info", {}).get("nickname", "匿名"),
                    content=c.get("content", ""),
                    likes=c.get("like_count", 0),
                )
                for c in comments_data[: self.comments_per_post]
            ]

    def _extract_detail_from_dom(self, post: Post) -> None:
        """Fallback: extract detail content from DOM."""
        try:
            content = self._page.evaluate("""() => {
                const desc = document.querySelector('.desc, .note-text, [class*="desc"]');
                if (desc) return desc.innerText.trim();
                return '';
            }""")
            if content:
                post.content += f"\n\n详情正文:\n{content}"

            # Try to get comments from DOM
            comments = self._page.evaluate("""() => {
                try {
                    const items = document.querySelectorAll('.comment-item, [class*="comment-item"]');
                    return Array.from(items).slice(0, 20).map(c => {
                        const author = c.querySelector('.name, [class*="name"]');
                        const text = c.querySelector('.content, [class*="content"]');
                        return {
                            author: author ? author.innerText.trim() : '匿名',
                            content: text ? text.innerText.trim() : '',
                        };
                    }).filter(c => c.content);
                } catch(e) { return []; }
            }""")
            if comments:
                post.comments = [
                    Comment(author=c["author"], content=c["content"], likes=0)
                    for c in comments
                ]
        except Exception:
            pass

    @staticmethod
    def _parse_count(text: str) -> int:
        text = str(text).strip()
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        try:
            return int(text)
        except ValueError:
            return 0

    def close(self) -> None:
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
