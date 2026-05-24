import json
from datetime import date

from src.ai.client import AIClient
from src.models.post import Post


SYSTEM_PROMPT = """你是一个专业的消费决策调研助手。用户会给你多从小红书搜索到的帖子数据，你需要分析这些帖子，生成一份实用的调研报告。

注意：部分帖子可能只有标题和点赞数（正文被限制），这种情况下请充分利用标题信息来推断内容。

报告结构：
1. **核心发现** — 3-5 句话总结关键观点和趋势
2. **推荐清单** — 如果提到具体产品/服务，列成表格（名称、价格区间、提及次数、主要优点/缺点）
3. **购买/决策建议** — 实用的行动指南
4. **踩坑提醒** — 用户反馈的负面信息或注意事项
5. **热门话题** — 讨论最多的子话题或关键词
6. **观点分布** — 正面/中性/负面的比例

输出格式：中文 Markdown。尽量具体、有数据支撑。如果信息不足以生成某个板块，标注"数据不足"并给出搜索建议。
"""

MERGE_PROMPT = """以下是对同一话题多组小红书帖子的独立摘要。请合并为一份完整、无重复的最终报告。

要求：
- 合并重复项，保留最有价值的信息
- 推荐清单要合并统计提及次数
- 保持 Markdown 格式，包含：核心发现、推荐清单（表格）、购买建议、踩坑提醒、热门话题、观点分布
- 中文输出
"""


def _posts_to_text(posts: list[Post]) -> str:
    parts = []
    for i, p in enumerate(posts, 1):
        section = f"--- 帖子 {i} ---\n"
        section += f"标题: {p.title}\n"
        section += f"点赞: {p.likes}\n"
        if p.content and p.content != p.title:
            section += f"内容: {p.content}\n"
        if p.comments:
            section += "热门评论:\n"
            for c in p.comments[:5]:
                section += f"  - @{c.author}: {c.content}\n"
        parts.append(section)
    return "\n\n".join(parts)


def _chunk_posts(posts: list[Post], chunk_size: int = 10) -> list[list[Post]]:
    return [posts[i:i + chunk_size] for i in range(0, len(posts), chunk_size)]


class Summarizer:
    def __init__(self, client: AIClient):
        self.client = client

    def generate_report(self, keyword: str, posts: list[Post],
                        related_searches: list[str] | None = None) -> str:
        if not posts:
            return f"# {keyword}\n\n未找到相关帖子。"

        chunks = _chunk_posts(posts)
        keyword_hint = f"\n\n相关搜索建议: {', '.join(related_searches)}" if related_searches else ""

        if len(chunks) == 1:
            return self._summarize_group(keyword, chunks[0], is_final=True) + keyword_hint
        else:
            group_summaries = []
            for i, chunk in enumerate(chunks):
                partial = self._summarize_group(keyword, chunk, is_final=False)
                group_summaries.append(f"## 第 {i+1} 组摘要\n\n{partial}")
            merged = self._merge_summaries(keyword, "\n\n".join(group_summaries))
            return merged + keyword_hint

    def _summarize_group(self, keyword: str, posts: list[Post], is_final: bool) -> str:
        user_content = f"搜索关键词: {keyword}\n帖子数量: {len(posts)}\n\n{_posts_to_text(posts)}"
        system = SYSTEM_PROMPT
        if not is_final:
            system += "\n\n这是部分帖子的摘要，请输出精简摘要供后续合并。重点提取：推荐项、价格、优缺点、关键观点。"

        resp = self.client.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ])

        if is_final:
            header = f"# {keyword} 调研报告\n\n> 基于 {len(posts)} 篇小红书帖子 · {date.today()}\n\n"
            return header + resp
        return resp

    def _merge_summaries(self, keyword: str, combined: str) -> str:
        resp = self.client.chat([
            {"role": "system", "content": MERGE_PROMPT},
            {"role": "user", "content": combined},
        ])
        return f"# {keyword} 调研报告\n\n{resp}"
