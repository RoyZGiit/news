"""Reddit data source: hot posts from AI-related subreddits using PRAW."""

import json
import logging
import os
from datetime import datetime, timezone

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
        """Fetch hot posts from configured subreddits."""
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
