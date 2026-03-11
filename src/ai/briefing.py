"""Briefing generator: aggregates articles and generates daily/weekly briefings."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from src.ai.llm_client import call_llm
from src.config import get_config
from src.database import Article, Briefing, get_session

logger = logging.getLogger(__name__)

BRIEFING_SYSTEM_PROMPT = """你是一位资深AI行业分析师，负责编写每日AI行业简报。

要求：
1. 使用中文撰写
2. 按以下分类组织内容：
   - 🔥 重要动态（重大发布、突破性进展）
   - 📝 论文亮点（值得关注的新论文）
   - 🛠️ 开源项目（热门新项目、重要版本更新）
   - 💬 社区热议（Reddit、Twitter上的热门讨论）
   - 📊 排行榜变化（Benchmark变动、新纪录）
   - 📰 行业新闻（厂商博客更新、行业动态）
3. 每个分类下的条目应包含：标题、简短摘要（1-2句话）、来源链接
4. 如果某个分类没有内容，可以跳过
5. 开头写一段总结（3-5句话），概述今日AI领域最重要的进展
6. 使用Markdown格式

请生成一篇专业、信息密度高、易于阅读的AI行业简报。"""

BRIEFING_SYSTEM_PROMPT_EN = """You are a senior AI industry analyst responsible for writing AI industry briefings.

Requirements:
1. Write in English
2. Organize content by the following categories:
   - 🔥 Key Highlights (major releases, breakthroughs)
   - 📝 Notable Papers (papers worth following)
   - 🛠️ Open Source (trending new projects, major version updates)
   - 💬 Community Buzz (hot discussions on Reddit, Twitter)
   - 📊 Leaderboard Changes (benchmark shifts, new records)
   - 📰 Industry News (vendor blog updates, industry developments)
3. Each item should include: title, brief summary (1-2 sentences), source link
4. Skip categories that have no content
5. Start with a summary paragraph (3-5 sentences) highlighting the most important developments
6. Use Markdown format

Generate a professional, information-dense, and easy-to-read AI industry briefing."""

BRIEFING_USER_TEMPLATE = """以下是过去{period}收集到的AI行业重要资讯（按重要性排序）：

{articles_text}

请基于以上资讯，生成一篇{period_name}简报。日期：{date}"""

BRIEFING_USER_TEMPLATE_EN = """Below are important AI industry updates collected over the past {period} (sorted by importance):

{articles_text}

Based on the above, generate a {period_name} briefing. Date: {date}"""


def _format_articles_for_prompt(articles: list[Article], lang: str = "zh") -> str:
    """Format articles into text for the LLM prompt.

    Args:
        articles: List of articles to format.
        lang: Language variant — 'zh' for Chinese, 'en' for English.
    """
    lines = []
    for i, art in enumerate(articles, 1):
        if lang == "en":
            summary = art.summary_en or art.summary or art.content or ""
            title = art.ai_title_en or art.title
        else:
            summary = art.summary or art.content or ""
            title = art.ai_title or art.title
        if len(summary) > 200:
            summary = summary[:200] + "..."
        score = art.importance_score or 3.0
        summary_label = "Summary" if lang == "en" else "摘要"
        link_label = "Link" if lang == "en" else "链接"
        importance_label = "Importance" if lang == "en" else "重要性"
        lines.append(
            f"{i}. [{art.source}] {title}\n"
            f"   {summary_label}: {summary}\n"
            f"   {link_label}: {art.url}\n"
            f"   {importance_label}: {score}/5"
        )
    return "\n\n".join(lines)


async def generate_daily_briefing(
    target_date: Optional[datetime] = None,
) -> Optional[Briefing]:
    """Generate a daily briefing for the given date (defaults to today)."""
    config = get_config().llm
    session = get_session()

    try:
        if target_date is None:
            target_date = datetime.now(timezone.utc)

        date_str = target_date.strftime("%Y-%m-%d")

        # Check if briefing already exists
        existing = session.execute(
            select(Briefing).where(
                Briefing.date == date_str, Briefing.period == "daily"
            )
        ).scalar_one_or_none()
        if existing:
            logger.info(f"Daily briefing for {date_str} already exists, skipping.")
            return existing

        # Fetch articles from the last 24 hours that passed judgment (skip ignored)
        since = target_date - timedelta(hours=24)
        stmt = (
            select(Article)
            .where(
                Article.fetched_at >= since,
                Article.ignored != 1,  # Skip ignored articles
                Article.ai_title.isnot(None),  # Must have passed judgment
            )
            .order_by(Article.importance_score.desc().nullslast())
            .limit(20)
        )
        articles = session.execute(stmt).scalars().all()

        if not articles:
            logger.warning(f"No articles found for daily briefing on {date_str}.")
            return None

        # --- Generate Chinese briefing ---
        articles_text_zh = _format_articles_for_prompt(articles, lang="zh")
        prompt_zh = BRIEFING_USER_TEMPLATE.format(
            period="24小时",
            articles_text=articles_text_zh,
            period_name="每日",
            date=date_str,
        )

        logger.info(
            f"Generating daily briefing for {date_str} with {len(articles)} articles..."
        )
        content_md = await call_llm(
            prompt=prompt_zh,
            system_prompt=BRIEFING_SYSTEM_PROMPT,
            model=config.briefing_model,
            temperature=0.3,
            max_tokens=4096,
        )

        # Pause before the English call to avoid rate limits
        await asyncio.sleep(3.0)

        # --- Generate English briefing ---
        articles_text_en = _format_articles_for_prompt(articles, lang="en")
        prompt_en = BRIEFING_USER_TEMPLATE_EN.format(
            period="24 hours",
            articles_text=articles_text_en,
            period_name="daily",
            date=date_str,
        )

        logger.info(f"Generating English daily briefing for {date_str}...")
        content_md_en = await call_llm(
            prompt=prompt_en,
            system_prompt=BRIEFING_SYSTEM_PROMPT_EN,
            model=config.briefing_model,
            temperature=0.3,
            max_tokens=4096,
        )

        briefing = Briefing(
            date=date_str,
            period="daily",
            title=f"AI 行业日报 - {date_str}",
            title_en=f"AI Daily Briefing - {date_str}",
            content_markdown=content_md,
            content_markdown_en=content_md_en,
            article_count=len(articles),
            created_at=datetime.now(timezone.utc),
        )
        session.add(briefing)
        session.commit()
        
        # Refresh to load all attributes before session closes
        session.refresh(briefing)

        logger.info(f"Daily briefing generated for {date_str}.")
        return briefing

    except Exception as e:
        logger.error(f"Failed to generate daily briefing: {e}", exc_info=True)
        session.rollback()
        return None
    finally:
        session.close()


async def generate_weekly_briefing(
    target_date: Optional[datetime] = None,
) -> Optional[Briefing]:
    """Generate a weekly briefing for the week ending on the given date."""
    config = get_config().llm
    session = get_session()

    try:
        if target_date is None:
            target_date = datetime.now(timezone.utc)

        date_str = target_date.strftime("%Y-%m-%d")

        existing = session.execute(
            select(Briefing).where(
                Briefing.date == date_str, Briefing.period == "weekly"
            )
        ).scalar_one_or_none()
        if existing:
            logger.info(f"Weekly briefing for {date_str} already exists, skipping.")
            return existing

        # Fetch articles from the last 7 days that passed judgment (skip ignored)
        since = target_date - timedelta(days=7)
        stmt = (
            select(Article)
            .where(
                Article.fetched_at >= since,
                Article.ignored != 1,  # Skip ignored articles
                Article.ai_title.isnot(None),  # Must have passed judgment
            )
            .order_by(Article.importance_score.desc().nullslast())
            .limit(30)
        )
        articles = session.execute(stmt).scalars().all()

        if not articles:
            logger.warning(f"No articles found for weekly briefing on {date_str}.")
            return None

        # --- Generate Chinese briefing ---
        articles_text_zh = _format_articles_for_prompt(articles, lang="zh")
        prompt_zh = BRIEFING_USER_TEMPLATE.format(
            period="一周",
            articles_text=articles_text_zh,
            period_name="每周",
            date=date_str,
        )

        logger.info(
            f"Generating weekly briefing for {date_str} with {len(articles)} articles..."
        )
        content_md = await call_llm(
            prompt=prompt_zh,
            system_prompt=BRIEFING_SYSTEM_PROMPT,
            model=config.briefing_model,
            temperature=0.3,
            max_tokens=8000,
        )

        # Pause before the English call to avoid rate limits
        await asyncio.sleep(3.0)

        # --- Generate English briefing ---
        articles_text_en = _format_articles_for_prompt(articles, lang="en")
        prompt_en = BRIEFING_USER_TEMPLATE_EN.format(
            period="one week",
            articles_text=articles_text_en,
            period_name="weekly",
            date=date_str,
        )

        logger.info(f"Generating English weekly briefing for {date_str}...")
        content_md_en = await call_llm(
            prompt=prompt_en,
            system_prompt=BRIEFING_SYSTEM_PROMPT_EN,
            model=config.briefing_model,
            temperature=0.3,
            max_tokens=8000,
        )

        briefing = Briefing(
            date=date_str,
            period="weekly",
            title=f"AI 行业周报 - {date_str}",
            title_en=f"AI Weekly Briefing - {date_str}",
            content_markdown=content_md,
            content_markdown_en=content_md_en,
            article_count=len(articles),
            created_at=datetime.now(timezone.utc),
        )
        session.add(briefing)
        session.commit()
        
        # Refresh to load all attributes before session closes
        session.refresh(briefing)

        logger.info(f"Weekly briefing generated for {date_str}.")
        return briefing

    except Exception as e:
        logger.error(f"Failed to generate weekly briefing: {e}", exc_info=True)
        session.rollback()
        return None
    finally:
        session.close()
