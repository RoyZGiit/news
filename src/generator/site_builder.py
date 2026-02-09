"""Static HTML site builder: renders briefings into static HTML files using Jinja2."""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select

from src.config import SITE_DIR, TEMPLATES_DIR, get_config
from src.database import Article, Briefing, SourceStatus, get_session

logger = logging.getLogger(__name__)


def _get_jinja_env() -> Environment:
    """Create Jinja2 environment with template directory."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )


def _md_to_html(md_text: str) -> str:
    """Convert Markdown text to HTML."""
    return markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "nl2br"],
    )


def build_site() -> None:
    """Build the complete static site from database content."""
    config = get_config()
    session = get_session()
    env = _get_jinja_env()

    try:
        # Ensure site directory exists
        SITE_DIR.mkdir(parents=True, exist_ok=True)

        # Copy static assets
        static_src = TEMPLATES_DIR / "static"
        static_dst = SITE_DIR / "static"
        if static_src.exists():
            if static_dst.exists():
                shutil.rmtree(static_dst)
            shutil.copytree(static_src, static_dst)

        # Fetch all briefings ordered by date
        stmt = select(Briefing).order_by(Briefing.date.desc())
        briefings = session.execute(stmt).scalars().all()

        # Fetch latest articles for the index page — only important articles (passed judgment)
        stmt = (
            select(Article)
            .where(
                Article.ignored != 1,
                Article.ai_title.isnot(None)
            )
            .order_by(Article.importance_score.desc().nullslast(), Article.fetched_at.desc())
            .limit(15)
        )
        latest_articles = session.execute(stmt).scalars().all()

        # Fetch source statuses
        source_statuses = session.execute(select(SourceStatus)).scalars().all()

        # Common template context
        site_ctx = {
            "site_title": config.publish.site_title,
            "site_description": config.publish.site_description,
            "site_url": config.publish.site_url,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }

        # --- Build index.html ---
        latest_briefing = briefings[0] if briefings else None
        latest_html = ""
        if latest_briefing:
            latest_html = _md_to_html(latest_briefing.content_markdown)

        index_template = env.get_template("index.html")
        index_html = index_template.render(
            **site_ctx,
            latest_briefing=latest_briefing,
            latest_briefing_html=latest_html,
            latest_articles=latest_articles,
            recent_briefings=briefings[:10],
            source_statuses=source_statuses,
        )
        (SITE_DIR / "index.html").write_text(index_html, encoding="utf-8")

        # --- Build individual briefing pages ---
        briefing_template = env.get_template("briefing.html")
        for briefing in briefings:
            briefing_html_content = _md_to_html(briefing.content_markdown)
            briefing_html_content_en = ""
            if briefing.content_markdown_en:
                briefing_html_content_en = _md_to_html(briefing.content_markdown_en)
            page_html = briefing_template.render(
                **site_ctx,
                briefing=briefing,
                briefing_html=briefing_html_content,
                briefing_html_en=briefing_html_content_en,
            )
            filename = f"briefing-{briefing.period}-{briefing.date}.html"
            (SITE_DIR / filename).write_text(page_html, encoding="utf-8")

        # --- Build archive.html ---
        archive_template = env.get_template("archive.html")
        daily_briefings = [b for b in briefings if b.period == "daily"]
        weekly_briefings = [b for b in briefings if b.period == "weekly"]
        archive_html = archive_template.render(
            **site_ctx,
            daily_briefings=daily_briefings,
            weekly_briefings=weekly_briefings,
        )
        (SITE_DIR / "archive.html").write_text(archive_html, encoding="utf-8")

        # --- Build JSON API (for potential future use) ---
        api_data = {
            "site": {
                "title": config.publish.site_title,
                "generated_at": site_ctx["generated_at"],
            },
            "latest_briefing": {
                "date": latest_briefing.date if latest_briefing else None,
                "title": latest_briefing.title if latest_briefing else None,
                "period": latest_briefing.period if latest_briefing else None,
            },
            "briefings": [
                {
                    "date": b.date,
                    "period": b.period,
                    "title": b.title,
                    "article_count": b.article_count,
                    "url": f"briefing-{b.period}-{b.date}.html",
                }
                for b in briefings[:30]
            ],
        }
        (SITE_DIR / "api.json").write_text(
            json.dumps(api_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(
            f"Static site built: {len(briefings)} briefing pages + index + archive"
        )

    finally:
        session.close()
