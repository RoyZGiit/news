@cli.command()
def pipeline() -> None:
    """Run the full pipeline: crawl -> summarize -> briefing -> build -> push."""
    from src.scheduler import run_all_crawlers
    from src.ai.summarizer import summarize_unsummarized
    from src.ai.briefing import generate_daily_briefing
    from src.generator.markdown_gen import save_briefing_markdown
    from src.generator.site_builder import build_site
    from src.publisher.rsync_push import push_to_remote

    logger = logging.getLogger(__name__)

    async def _pipeline():
        logger.info("=== Step 1/4: Crawling ===")
        await run_all_crawlers()

        logger.info("=== Step 2/4: Summarizing (top 15 articles) ===")
        await summarize_unsummarized(batch_size=15)

        logger.info("=== Step 3/4: Generating briefing ===")
        result = await generate_daily_briefing()
        if result:
            save_briefing_markdown(result)

        logger.info("=== Step 4/4: Building and pushing ===")
        build_site()
        push_to_remote()

        logger.info("=== Pipeline complete ===")

    asyncio.run(_pipeline())
