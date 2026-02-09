"""APScheduler task orchestration: schedules crawlers, summarization, and briefing generation."""

import asyncio
import logging


from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.config import get_config
from src.sources.github_source import GitHubCrawler
from src.sources.huggingface_source import HuggingFaceCrawler
from src.sources.reddit_source import RedditCrawler
from src.sources.twitter_source import TwitterCrawler
from src.sources.arxiv_source import ArxivCrawler
from src.sources.leaderboard_source import LeaderboardCrawler
from src.sources.hackernews_source import HackerNewsCrawler
from src.sources.website_source import WebsiteCrawler
from src.ai.summarizer import summarize_unsummarized
from src.ai.judgment import process_articles
from src.ai.briefing import generate_daily_briefing, generate_weekly_briefing
from src.generator.markdown_gen import save_briefing_markdown
from src.generator.site_builder import build_site
from src.publisher.rsync_push import push_to_remote

logger = logging.getLogger(__name__)


async def run_crawler(crawler_class: type) -> None:
    """Instantiate and run a crawler."""
    crawler = crawler_class()
    await crawler.run()


async def run_summarization() -> None:
    """Run AI summarization on unsummarized articles."""
    logger.info("Running summarization task...")
    count = await summarize_unsummarized(batch_size=20)
    logger.info(f"Summarization complete: {count} articles processed.")


async def run_daily_briefing() -> None:
    """Generate daily briefing, build site, and push to remote."""
    logger.info("Running daily briefing generation...")

    # First, summarize any remaining articles
    await run_summarization()

    # Generate the briefing
    briefing = await generate_daily_briefing()
    if briefing:
        # Save as markdown file
        save_briefing_markdown(briefing)

        # Build static site
        build_site()

        # Push to remote server
        push_to_remote()

    logger.info("Daily briefing pipeline complete.")


async def run_weekly_briefing() -> None:
    """Generate weekly briefing, build site, and push to remote."""
    logger.info("Running weekly briefing generation...")

    briefing = await generate_weekly_briefing()
    if briefing:
        save_briefing_markdown(briefing)
        build_site()
        push_to_remote()

    logger.info("Weekly briefing pipeline complete.")


async def run_all_crawlers() -> None:
    """Run all enabled crawlers sequentially with pauses in between."""
    config = get_config().sources

    crawlers: list[tuple[str, type, bool]] = [
        ("github", GitHubCrawler, config.github.enabled),
        ("huggingface", HuggingFaceCrawler, config.huggingface.enabled),
        ("reddit", RedditCrawler, config.reddit.enabled),
        ("twitter", TwitterCrawler, config.twitter.enabled),
        ("hackernews", HackerNewsCrawler, config.hackernews.enabled),
        ("arxiv", ArxivCrawler, config.arxiv.enabled),
        ("leaderboard", LeaderboardCrawler, config.leaderboard.enabled),
        ("websites", WebsiteCrawler, config.websites.enabled),
    ]

    ran_any = False
    for name, cls, enabled in crawlers:
        if enabled:
            # Pause between crawlers to spread out requests
            if ran_any:
                logger.debug("[scheduler] Pausing 5s between crawlers...")
                await asyncio.sleep(5.0)
            await run_crawler(cls)
            ran_any = True
        else:
            logger.debug(f"[scheduler] Skipping disabled source: {name}")

    # NOTE: Summarization is now handled by the main pipeline (judgment first)
    
    # Run judgment on newly fetched articles
    from src.database import Article, get_session
    session = get_session()
    try:
        new_articles = session.query(Article).filter(
            Article.ignored == 0,
            Article.ai_title.is_(None)
        ).order_by(Article.fetched_at.desc()).limit(30).all()
        if new_articles:
            import asyncio
            asyncio.run(process_articles(new_articles))
            session.commit()
    finally:
        session.close()


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler with all jobs."""
    config = get_config()
    scheduler = AsyncIOScheduler()

    sources = config.sources

    # --- Source crawlers ---
    if sources.github.enabled:
        scheduler.add_job(
            run_crawler,
            IntervalTrigger(hours=sources.github.interval_hours),
            args=[GitHubCrawler],
            id="crawl_github",
            name="GitHub Crawler",
        )

    if sources.huggingface.enabled:
        scheduler.add_job(
            run_crawler,
            IntervalTrigger(hours=sources.huggingface.interval_hours),
            args=[HuggingFaceCrawler],
            id="crawl_huggingface",
            name="HuggingFace Crawler",
        )

    if sources.reddit.enabled:
        scheduler.add_job(
            run_crawler,
            IntervalTrigger(hours=sources.reddit.interval_hours),
            args=[RedditCrawler],
            id="crawl_reddit",
            name="Reddit Crawler",
        )

    if sources.twitter.enabled:
        scheduler.add_job(
            run_crawler,
            IntervalTrigger(hours=sources.twitter.interval_hours),
            args=[TwitterCrawler],
            id="crawl_twitter",
            name="Twitter Crawler",
        )

    if sources.hackernews.enabled:
        scheduler.add_job(
            run_crawler,
            IntervalTrigger(hours=sources.hackernews.interval_hours),
            args=[HackerNewsCrawler],
            id="crawl_hackernews",
            name="Hacker News Crawler",
        )

    if sources.arxiv.enabled:
        scheduler.add_job(
            run_crawler,
            IntervalTrigger(hours=sources.arxiv.interval_hours),
            args=[ArxivCrawler],
            id="crawl_arxiv",
            name="Arxiv Crawler",
        )

    if sources.leaderboard.enabled:
        scheduler.add_job(
            run_crawler,
            IntervalTrigger(hours=sources.leaderboard.interval_hours),
            args=[LeaderboardCrawler],
            id="crawl_leaderboard",
            name="Leaderboard Crawler",
        )

    if sources.websites.enabled:
        scheduler.add_job(
            run_crawler,
            IntervalTrigger(hours=sources.websites.interval_hours),
            args=[WebsiteCrawler],
            id="crawl_websites",
            name="Website Blog Crawler",
        )

    # --- Summarization (runs every 2 hours) ---
    scheduler.add_job(
        run_summarization,
        IntervalTrigger(hours=2),
        id="summarize",
        name="AI Summarization",
    )

    # --- Daily briefing ---
    hour, minute = config.scheduler.daily_briefing_time.split(":")
    scheduler.add_job(
        run_daily_briefing,
        CronTrigger(hour=int(hour), minute=int(minute)),
        id="daily_briefing",
        name="Daily Briefing Generator",
    )

    # --- Weekly briefing (on configured day) ---
    day_map = {
        "monday": "mon",
        "tuesday": "tue",
        "wednesday": "wed",
        "thursday": "thu",
        "friday": "fri",
        "saturday": "sat",
        "sunday": "sun",
    }
    day = day_map.get(config.scheduler.weekly_briefing_day.lower(), "mon")
    scheduler.add_job(
        run_weekly_briefing,
        CronTrigger(day_of_week=day, hour=int(hour), minute=int(minute) + 30),
        id="weekly_briefing",
        name="Weekly Briefing Generator",
    )

    return scheduler
