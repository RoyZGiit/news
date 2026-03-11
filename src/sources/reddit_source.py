"""Reddit data source: hot posts from AI-related subreddits using PRAW or RSS."""

import json
import logging
import os
from datetime import datetime, timezone

import feedparser

from src.config import get_config
from src.database import Article
from src.sources.base import BaseCrawler

logger = logging.getLogger(__name__)


class RedditCrawler(BaseCrawler):
    source_name = "reddit"

    def __init__(self) -> None:
        super().__init__()
        self.config = get_config().sources.reddit

    async def fetch(self) -> list[Article]:
        """Fetch hot posts from configured subreddits via PRAW or RSS."""
        method = getattr(self.config, "method", "praw")
        
        if method == "rss":
            return await self._fetch_via_rss()
        else:
            return await self._fetch_via_praw()

    async def _fetch_via_rss(self) -> list[Article]:
        """Fetch posts via RSS feeds (no auth required)."""
        articles = []
        base = "https://www.reddit.com"
        
        for subreddit_name in self.config.subreddits:
            try:
                rss_url = f"{base}/r/{subreddit_name}/.rss"
                resp = await self.throttled_get(rss_url, timeout=15.0)
                resp.raise_for_status()

                feed = feedparser.parse(resp.text)

                for entry in feed.entries[:self.config.post_limit]:
                    try:
                        pub_dt = None
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            pub_dt = datetime(
                                *entry.published_parsed[:6], tzinfo=timezone.utc
                            )

                        # Extract Reddit ID from guid or link
                        reddit_id = entry.get("id", entry.get("link", "").split("/")[-3] if "/" in entry.get("link", "") else "")
                        
                        # Get content from summary or description
                        content = entry.get("summary", entry.get("description", ""))[:2000]
                        
                        # Clean content (remove HTML tags if present)
                        import re
                        content = re.sub(r'<[^>]+>', '', content)
                        
                        articles.append(
                            Article(
                                source=self.source_name,
                                source_id=f"reddit-{reddit_id}",
                                title=f"[r/{subreddit_name}] {entry.get('title', '')}",
                                url=entry.get("link", ""),
                                content=content,
                                category="discussion",
                                author=entry.get("author", "unknown"),
                                tags=subreddit_name,
                                extra_data=json.dumps({
                                    "subreddit": subreddit_name,
                                }),
                                published_at=pub_dt,
                                fetched_at=self.now_utc(),
                            )
                        )
                    except Exception as e:
                        logger.warning(f"[reddit] Failed to parse entry from r/{subreddit_name}: {e}")
                        
            except Exception as e:
                logger.warning(f"[reddit] Failed to fetch r/{subreddit_name}: {e}")

        return articles

    async def _fetch_via_praw(self) -> list[Article]:
        """Fetch posts via PRAW (requires API credentials)."""
        import praw

        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        user_agent = os.getenv("REDDIT_USER_AGENT", "ai-news-aggregator/1.0")

        if not client_id or not client_secret:
            logger.warning("[reddit] Missing REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET, skipping.")
            return []

        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )

        articles = []
        for subreddit_name in self.config.subreddits:
            try:
                subreddit = reddit.subreddit(subreddit_name)
                for post in subreddit.hot(limit=self.config.post_limit):
                    # Skip stickied posts
                    if post.stickied:
                        continue

                    content = post.selftext[:2000] if post.selftext else ""
                    pub_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)

                    articles.append(
                        Article(
                            source=self.source_name,
                            source_id=f"reddit-{post.id}",
                            title=f"[r/{subreddit_name}] {post.title}",
                            url=f"https://reddit.com{post.permalink}",
                            content=content,
                            category="discussion",
                            author=str(post.author) if post.author else "deleted",
                            tags=subreddit_name,
                            extra_data=json.dumps(
                                {
                                    "score": post.score,
                                    "num_comments": post.num_comments,
                                    "upvote_ratio": post.upvote_ratio,
                                    "subreddit": subreddit_name,
                                }
                            ),
                            published_at=pub_dt,
                            fetched_at=self.now_utc(),
                        )
                    )
            except Exception as e:
                logger.warning(f"[reddit] Failed to fetch r/{subreddit_name}: {e}")

        return articles
