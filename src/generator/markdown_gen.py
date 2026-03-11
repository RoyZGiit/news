"""Markdown file generator: saves briefings as Markdown files to briefings/ directory."""

import logging
from pathlib import Path

from src.config import BRIEFINGS_DIR
from src.database import Briefing

logger = logging.getLogger(__name__)


def save_briefing_markdown(briefing: Briefing) -> Path:
    """Save a briefing as a Markdown file.

    Returns the path to the generated file.
    """
    filename = f"{briefing.period}-{briefing.date}.md"
    filepath = BRIEFINGS_DIR / filename

    header = f"# {briefing.title}\n\n"
    header += f"> 生成时间: {briefing.created_at}\n"
    header += f"> 文章数量: {briefing.article_count}\n\n"
    header += "---\n\n"

    content = header + briefing.content_markdown

    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Saved briefing to {filepath}")
    return filepath
