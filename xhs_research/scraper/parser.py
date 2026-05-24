import re
import time

from playwright.sync_api import Page
from rich.console import Console

from xhs_research.models.post import Post, Comment

console = Console()


class XiaohongshuScraper:
    def __init__(self, page: Page, comments_per_post: int = 20):
        self.page = page
        self.comments_per_post = comments_per_post
        self.related_searches: list[str] = []
        self._detail_blocked = False

    def search(self, keyword: str, limit: int = 20) -> list[Post]:
        """从当前搜索结果页提取帖子。cli.py 已负责导航和登录。"""
        console.print(f"[cyan]提取搜索结果: {keyword}[/cyan]")
        time.sleep(2)

        posts: list[Post] = []
        seen_ids: set[str] = set()
        no_new_count = 0

        while len(posts) < limit:
            cards = self.page.query_selector_all("section.note-item")
            new_in_round = 0

            for card in cards:
                if len(posts) >= limit:
                    break
                post = self._parse_card(card)
                if post and post.id not in seen_ids:
                    seen_ids.add(post.id)
                    posts.append(post)
                    new_in_round += 1
                    console.print(f"  [{len(posts)}/{limit}] {post.title[:50]}...")

            if new_in_round == 0:
                no_new_count += 1
                if no_new_count >= 3:
                    console.print(f"[yellow]已无新内容，停止翻页。共 {len(posts)} 个帖子[/yellow]")
                    break
            else:
                no_new_count = 0

            if len(posts) < limit:
                self.page.evaluate("window.scrollBy(0, 2000)")
                time.sleep(1.5)

        # 抓取"大家都在搜"
        self._extract_related_searches()

        # 尝试获取详情
        self._try_fetch_details(posts)

        return posts

    def _parse_card(self, card) -> Post | None:
        try:
            # 提取帖子 ID
            explore_link = card.query_selector("a[href*='/explore/']")
            href = (explore_link.get_attribute("href") or "") if explore_link else ""
            note_match = re.search(r"/explore/([a-f0-9]+)", href)
            if not note_match:
                link = card.query_selector("a.cover.mask")
                href2 = (link.get_attribute("href") or "") if link else ""
                note_match = re.search(r"/search_result/([a-f0-9]+)", href2)
            if not note_match:
                return None
            note_id = note_match.group(1)

            # 提取标题
            title_el = card.query_selector(".title span, .note-title, span.title")
            title = title_el.inner_text().strip() if title_el else "(无标题)"

            # 提取点赞数
            likes_el = card.query_selector(".like-wrapper .count, span.likeCount")
            likes_text = likes_el.inner_text().strip() if likes_el else "0"
            likes = self._parse_count(likes_text)

            # 提取作者
            author_el = card.query_selector(".author .name, .author-wrapper .name, a[href*='/user/']")
            author = author_el.inner_text().strip() if author_el else ""

            # 提取标签
            tags = []
            tag_els = card.query_selector_all(".tag, [class*='tag']")
            for t in tag_els:
                txt = t.inner_text().strip()
                if txt and len(txt) < 20:
                    tags.append(txt)

            # 组合内容：标题 + 作者 + 标签 + 卡片全部文本
            card_text = card.inner_text().strip()
            parts = [f"标题: {title}"]
            if author:
                parts.append(f"作者: {author}")
            if likes > 0:
                parts.append(f"点赞: {likes}")
            if tags:
                parts.append(f"标签: {', '.join(tags)}")
            # 追加卡片原始文本（包含更多上下文）
            parts.append(f"原文摘要: {card_text}")

            return Post(
                id=note_id,
                title=title,
                content="\n".join(parts),
                likes=likes,
                author=author,
                url=f"https://www.rednote.com/explore/{note_id}",
                tags=tags,
            )
        except Exception:
            return None

    def _extract_related_searches(self) -> None:
        """提取'大家都在搜'相关搜索词。"""
        try:
            self.related_searches = self.page.evaluate("""() => {
                const items = document.querySelectorAll('.search-hot-item, [class*="related-search"] span, .hot-item');
                return Array.from(items).slice(0, 10).map(el => el.innerText.trim()).filter(t => t.length > 0 && t.length < 20);
            }""")
            if self.related_searches:
                console.print(f"[cyan]发现 {len(self.related_searches)} 个相关搜索词: {', '.join(self.related_searches[:5])}[/cyan]")
        except Exception:
            self.related_searches = []

    def _try_fetch_details(self, posts: list[Post]) -> None:
        """尝试批量获取帖子详情。如果第一次被限制则全部跳过。"""
        if self._detail_blocked:
            console.print("[yellow]详情页已被限制，跳过全部详情获取[/yellow]")
            return

        success = 0
        for i, post in enumerate(posts):
            console.print(f"[cyan]获取详情 ({i+1}/{len(posts)}): {post.title[:30]}...[/cyan]")
            if self._fetch_detail(post):
                success += 1
            else:
                # 被限制，不再尝试后续帖子
                console.print(f"[yellow]详情页被限制，跳过剩余 {len(posts)-i-1} 个帖子[/yellow]")
                break

        console.print(f"[cyan]详情获取: {success}/{len(posts)} 成功[/cyan]")

    def _fetch_detail(self, post: Post) -> bool:
        """尝试打开帖子详情页。返回 False 表示被限制。"""
        try:
            self.page.goto(post.url, wait_until="domcontentloaded")
            time.sleep(2)

            restricted = self.page.evaluate("""() => {
                const text = document.body.innerText;
                return text.includes('暂时无法浏览') || text.includes('扫码查看');
            }""")

            if restricted:
                self._detail_blocked = True
                return False

            # 提取正文
            content = self.page.evaluate("""() => {
                const desc = document.querySelector('.desc, .note-text, [class*="desc"]');
                if (desc) return desc.innerText.trim();
                return '';
            }""")

            if content:
                # 保留已有的结构化信息，追加详情正文
                post.content += f"\n\n详情正文:\n{content}"

            # 提取评论
            comments = self.page.evaluate("""() => {
                try {
                    const items = document.querySelectorAll('.comment-item, [class*="comment-item"]');
                    return Array.from(items).slice(0, 20).map(c => {
                        const author = c.querySelector('.name, [class*="name"]');
                        const text = c.querySelector('.content, [class*="content"]');
                        return {
                            author: author ? author.innerText.trim() : '匿名',
                            content: text ? text.innerText.trim() : '',
                            likes: 0
                        };
                    });
                } catch(e) { return []; }
            }""")
            if comments:
                post.comments = [Comment(author=c["author"], content=c["content"], likes=c["likes"]) for c in comments]

            return True

        except Exception:
            return False

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.strip()
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        try:
            return int(text)
        except ValueError:
            return 0
