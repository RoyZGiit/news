#!/usr/bin/env python3
"""AI News Aggregator - Main entry point.

Usage:
    python main.py run          # Start scheduler (continuous mode)
    python main.py crawl        # Run all crawlers once
    python main.py summarize    # Run summarization on unsummarized articles
    python main.py briefing     # Generate daily briefing now
    python main.py build        # Build static site
    python main.py push         # Push site to remote server
    python main.py pipeline     # Full pipeline: crawl -> summarize -> briefing -> build -> push
"""

import asyncio
import logging
import signal
import sys

import click
from rich.logging import RichHandler

from src.config import get_config
from src.database import init_db


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )
    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """AI News Aggregator - AI 行业信息聚合系统"""
    setup_logging(verbose)
    init_db()


@cli.command()
def run() -> None:
    """Start the scheduler for continuous operation."""
    from src.scheduler import create_scheduler, run_all_crawlers

    logger = logging.getLogger(__name__)
    logger.info("Starting AI News Aggregator scheduler...")
    logger.info("Press Ctrl+C to stop.")

    scheduler = create_scheduler()
    loop = asyncio.new_event_loop()

    # Run initial crawl on startup
    logger.info("Running initial crawl on startup...")
    loop.run_until_complete(run_all_crawlers())

    scheduler.start()

    # Handle graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        loop.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


@cli.command()
def crawl() -> None:
    """Run all enabled crawlers once (full crawl)."""
    from src.scheduler import run_all_crawlers

    logger = logging.getLogger(__name__)
    logger.info("Running all crawlers (full crawl)...")
    asyncio.run(run_all_crawlers())
    logger.info("Crawling complete.")


@cli.command()
def incremental() -> None:
    """Fetch only NEW articles (skip existing by URL)."""
    from src.scheduler import run_all_crawlers
    from src.database import Article, get_session

    logger = logging.getLogger(__name__)
    logger.info("Running incremental crawl (new articles only)...")

    session = get_session()
    try:
        # Get existing URLs to skip
        existing = {a.url for a in session.query(Article.url).all()}
        logger.info(f"Skipping {len(existing)} existing articles...")
    finally:
        session.close()

    asyncio.run(run_all_crawlers())
    logger.info("Incremental crawl complete.")


@cli.command()
@click.option("--batch-size", default=30, help="Number of articles to summarize")
def summarize(batch_size: int) -> None:
    """Run AI summarization on unsummarized articles."""
    from src.ai.summarizer import summarize_unsummarized

    logger = logging.getLogger(__name__)
    logger.info(f"Summarizing up to {batch_size} articles...")
    count = asyncio.run(summarize_unsummarized(batch_size=batch_size))
    logger.info(f"Summarized {count} articles.")


@cli.command()
@click.option("--weekly", is_flag=True, help="Generate weekly briefing instead of daily")
def briefing(weekly: bool) -> None:
    """Generate a briefing (daily by default)."""
    from src.ai.briefing import generate_daily_briefing, generate_weekly_briefing
    from src.generator.markdown_gen import save_briefing_markdown

    logger = logging.getLogger(__name__)
    if weekly:
        logger.info("Generating weekly briefing...")
        result = asyncio.run(generate_weekly_briefing())
    else:
        logger.info("Generating daily briefing...")
        result = asyncio.run(generate_daily_briefing())

    if result:
        path = save_briefing_markdown(result)
        logger.info(f"Briefing saved to {path}")
    else:
        logger.warning("No briefing generated (no articles or already exists).")


@cli.command()
def build() -> None:
    """Build the static HTML site."""
    from src.generator.site_builder import build_site

    logger = logging.getLogger(__name__)
    logger.info("Building static site...")
    build_site()
    logger.info("Static site built in site/ directory.")


@cli.command()
def push() -> None:
    """Push the static site to the remote server."""
    from src.publisher.rsync_push import push_to_remote

    logger = logging.getLogger(__name__)
    logger.info("Pushing site to remote server...")
    success = push_to_remote()
    if success:
        logger.info("Push successful.")
    else:
        logger.error("Push failed. Check logs for details.")
        sys.exit(1)


@cli.command()
def pipeline() -> None:
    """Run the full pipeline: crawl -> judge+translate -> summarize -> briefing -> build -> push."""
    from src.scheduler import run_all_crawlers
    from src.ai.judgment import process_articles
    from src.ai.summarizer import summarize_unsummarized
    from src.ai.briefing import generate_daily_briefing
    from src.generator.markdown_gen import save_briefing_markdown
    from src.generator.site_builder import build_site
    from src.publisher.rsync_push import push_to_remote
    from src.database import Article, get_session

    logger = logging.getLogger(__name__)

    async def _pipeline():
        logger.info("=== Step 1/4: Crawling ===")
        await run_all_crawlers()

        logger.info("=== Step 2/4: Judgment + Translation (one pass) ===")
        session = get_session()
        try:
            unsummarized = session.query(Article).filter(
                (Article.summarized == 0) & (Article.ignored != 1)
            ).order_by(Article.fetched_at.desc()).limit(30).all()
            if unsummarized:
                await process_articles(unsummarized)
                session.commit()
        finally:
            session.close()

        logger.info("=== Step 3/4: Summarizing ===")
        await summarize_unsummarized(batch_size=10)

        logger.info("=== Step 4/4: Building and pushing ===")
        result = await generate_daily_briefing()
        if result:
            save_briefing_markdown(result)
        build_site()
        push_to_remote()

        logger.info("=== Pipeline complete ===")

    asyncio.run(_pipeline())


@cli.command()
def refresh() -> None:
    """Quick refresh: re-run summarization + briefing + build (no crawling)."""
    from src.ai.summarizer import summarize_unsummarized
    from src.ai.briefing import generate_daily_briefing
    from src.generator.markdown_gen import save_briefing_markdown
    from src.generator.site_builder import build_site
    from src.publisher.rsync_push import push_to_remote

    logger = logging.getLogger(__name__)

    async def _refresh():
        logger.info("=== Step 1/3: Re-running summarization ===")
        await summarize_unsummarized(batch_size=15)

        logger.info("=== Step 2/3: Generating briefing ===")
        result = await generate_daily_briefing()
        if result:
            save_briefing_markdown(result)

        logger.info("=== Step 3/3: Building and pushing ===")
        build_site()
        push_to_remote()

        logger.info("=== Refresh complete ===")

    asyncio.run(_refresh())


@cli.command()
def status() -> None:
    """Show current status of all data sources."""
    from sqlalchemy import select
    from src.database import get_session, SourceStatus, Article, Briefing

    session = get_session()
    try:
        statuses = session.execute(
            select(SourceStatus).order_by(SourceStatus.source_name)
        ).scalars().all()

        article_count = session.execute(select(Article)).scalars().all()
        briefing_count = session.execute(select(Briefing)).scalars().all()

        click.echo(f"\n📊 AI News Aggregator Status")
        click.echo(f"{'=' * 60}")
        click.echo(f"Total articles: {len(article_count)}")
        click.echo(f"Total briefings: {len(briefing_count)}")
        click.echo(f"\n{'Source':<20} {'Status':<10} {'Last Run':<20} {'Total':<8}")
        click.echo(f"{'-' * 60}")
        for s in statuses:
            last_run = s.last_run.strftime('%Y-%m-%d %H:%M') if s.last_run else '—'
            click.echo(
                f"{s.source_name:<20} {s.status:<10} {last_run:<20} {s.total_articles or 0:<8}"
            )
        click.echo()
    finally:
        session.close()


if __name__ == "__main__":
    cli()
