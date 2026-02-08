"""Twitter/X data source via RSSHub, Nitter, or direct RSS feeds."""

import logging
from datetime import datetime, timezone

import feedparser

from src.config import get_config
from src.database import Article
from src.sources.base import BaseCrawler

logger = logging.getLogger(__name__)


class TwitterCrawler(BaseCrawler):
    source_name = "twitter"

    # 2s between requests
    request_delay = 2.0

    def __init__(self) -> None:
        super().__init__()
        self.config = get_config().sources.twitter

    async def fetch(self) -> list[Article]:
        """Fetch tweets from configured accounts via RSSHub or Nitter."""
        articles = []
        method = getattr(self.config, "method", "nitter")
        
        if method == "nitter":
            base = getattr(self.config, "nitter_base", "https://nitter.net").rstrip("/")
            
            for account in self.config.accounts:
                try:
                    rss_url = f"{base}/{account}/rss"
                    resp = await self.throttled_get(rss_url, timeout=15.0)
                    resp.raise_for_status()

                    feed = feedparser.parse(resp.text)

                    for entry in feed.entries[:10]:
                        pub_dt = None
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            try:
                                pub_dt = datetime(
                                    *entry.published_parsed[:6], tzinfo=timezone.utc
                                )
                            except (ValueError, TypeError):
                                pass

                        title = entry.get("title", "")[:200]
                        content = entry.get("summary", entry.get("description", ""))[:1000]
                        link = entry.get("link", "")

                        articles.append(
                            Article(
                                source=self.source_name,
                                source_id=f"tweet-{account}-{link.split('/')[-1] if '/' in link else hash(title)}",
                                title=f"[Twitter @{account}] {title}",
                                url=link,
                                content=content,
                                category="tweet",
                                author=account,
                                tags="twitter",
                                published_at=pub_dt,
                                fetched_at=self.now_utc(),
                            )
                        )
                except Exception as e:
                    logger.warning(f"[twitter] Failed to fetch @{account}: {e}")
                    
        elif method == "rsshub":
            base = getattr(self.config, "rsshub_base", "https://rsshub.app").rstrip("/")

            for account in self.config.accounts:
                try:
                    rss_url = f"{base}/twitter/user/{account}"
                    resp = await self.throttled_get(rss_url, timeout=15.0)
                    resp.raise_for_status()

                    feed = feedparser.parse(resp.text)

                    for entry in feed.entries[:10]:
                        pub_dt = None
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            try:
                                pub_dt = datetime(
                                    *entry.published_parsed[:6], tzinfo=timezone.utc
                                )
                            except (ValueError, TypeError):
                                pass

                        title = entry.get("title", "")[:200]
                        content = entry.get("summary", entry.get("description", ""))[:1000]
                        link = entry.get("link", "")

                        articles.append(
                            Article(
                                source=self.source_name,
                                source_id=f"tweet-{account}-{link.split('/')[-1] if '/' in link else hash(title)}",
                                title=f"[Twitter @{account}] {title}",
                                url=link,
                                content=content,
                                category="tweet",
                                author=account,
                                tags="twitter",
                                published_at=pub_dt,
                                fetched_at=self.now_utc(),
                            )
                        )
                except Exception as e:
                    logger.warning(f"[twitter] Failed to fetch @{account}: {e}")
        else:
            logger.warning(f"[twitter] Method '{method}' not supported.")

        return articles
