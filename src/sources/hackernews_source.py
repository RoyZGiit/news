"""Hacker News data source via official Firebase API."""

import json
import logging
from datetime import datetime, timezone

from src.config import get_config
from src.database import Article
from src.sources.base import BaseCrawler

logger = logging.getLogger(__name__)

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"


class HackerNewsCrawler(BaseCrawler):
    source_name = "hackernews"

    def __init__(self) -> None:
        super().__init__()
        self.config = get_config().sources.hackernews

    async def fetch(self) -> list[Article]:
        """Fetch top stories from Hacker News."""
        articles = []
        
        try:
            # Get top stories IDs
            top_url = f"{HN_API_BASE}/topstories.json"
            resp = await self.throttled_get(top_url, timeout=15.0)
            resp.raise_for_status()
            story_ids = resp.json()[:self.config.post_limit]

            for story_id in story_ids:
                try:
                    item_url = f"{HN_API_BASE}/item/{story_id}.json"
                    item_resp = await self.throttled_get(item_url, timeout=10.0)
                    item_resp.raise_for_status()
                    story = item_resp.json()

                    if not story or story.get("type") != "story" or not story.get("url"):
                        continue

                    # Parse timestamp
                    pub_dt = None
                    if story.get("time"):
                        pub_dt = datetime.fromtimestamp(story["time"], tz=timezone.utc)

                    articles.append(
                        Article(
                            source=self.source_name,
                            source_id=f"hn-{story_id}",
                            title=story.get("title", "")[:200],
                            url=story.get("url", ""),
                            content=f"HN Score: {story.get('score', 0)} | by {story.get('by', 'unknown')} | {story.get('descendants', 0)} comments",
                            category="discussion",
                            author=story.get("by", "unknown"),
                            tags="hackernews",
                            extra_data=json.dumps({
                                "score": story.get("score", 0),
                                "descendants": story.get("descendants", 0),
                                "hn_id": story_id,
                            }),
                            published_at=pub_dt,
                            fetched_at=self.now_utc(),
                        )
                    )
                except Exception as e:
                    logger.warning(f"[hackernews] Failed to fetch story {story_id}: {e}")

        except Exception as e:
            logger.warning(f"[hackernews] Failed to fetch top stories: {e}")

        return articles
