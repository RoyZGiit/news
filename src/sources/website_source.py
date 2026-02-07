"""Website blog monitoring: general-purpose web page change detection via RSS or HTML."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import feedparser
from bs4 import BeautifulSoup

from src.config import get_config
from src.database import Article
from src.sources.base import BaseCrawler

logger = logging.getLogger(__name__)


class WebsiteCrawler(BaseCrawler):
    source_name = "websites"

    # Be polite to blog servers — 2s between requests
    request_delay = 2.0

    def __init__(self) -> None:
        super().__init__()
        self.config = get_config().sources.websites

    async def _fetch_via_rss(self, blog_name: str, rss_url: str) -> list[Article]:
        """Fetch blog posts via RSS feed."""
        articles = []

        try:
            resp = await self.throttled_get(rss_url, timeout=15.0)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)

            for entry in feed.entries[:10]:
                pub_dt = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        pass

                link = entry.get("link", "")
                title = entry.get("title", "Untitled")
                summary = entry.get("summary", entry.get("description", ""))
                # Strip HTML tags from summary
                if summary:
                    summary = BeautifulSoup(summary, "html.parser").get_text()[:1000]

                source_id = hashlib.md5(link.encode()).hexdigest()[:16]

                articles.append(
                    Article(
                        source=self.source_name,
                        source_id=f"blog-{source_id}",
                        title=f"[{blog_name}] {title}",
                        url=link,
                        content=summary,
                        category="blog",
                        author=blog_name,
                        tags="blog",
                        published_at=pub_dt,
                        fetched_at=self.now_utc(),
                    )
                )
        except Exception as e:
            logger.warning(f"[websites] RSS fetch failed for {blog_name}: {e}")

        return articles

    async def _fetch_via_html(self, blog_name: str, url: str) -> list[Article]:
        """Fetch blog posts by scraping the HTML page for article links."""
        articles = []

        try:
            resp = await self.throttled_get(url, timeout=15.0)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find article-like links (heuristic: look for <a> tags in <article>, <h2>, <h3>)
            seen_urls = set()
            for tag in soup.find_all(["article", "h2", "h3", "h4"]):
                link_tag = tag.find("a", href=True) if tag.name != "a" else tag
                if not link_tag:
                    continue

                href = link_tag.get("href", "")
                if not href or href in seen_urls:
                    continue

                # Make absolute URL
                if href.startswith("/"):
                    from urllib.parse import urljoin
                    href = urljoin(url, href)
                elif not href.startswith("http"):
                    continue

                seen_urls.add(href)
                title = link_tag.get_text(strip=True)[:200]
                if not title or len(title) < 5:
                    continue

                source_id = hashlib.md5(href.encode()).hexdigest()[:16]

                articles.append(
                    Article(
                        source=self.source_name,
                        source_id=f"blog-{source_id}",
                        title=f"[{blog_name}] {title}",
                        url=href,
                        content="",
                        category="blog",
                        author=blog_name,
                        tags="blog",
                        fetched_at=self.now_utc(),
                    )
                )

                if len(articles) >= 10:
                    break

        except Exception as e:
            logger.warning(f"[websites] HTML scrape failed for {blog_name}: {e}")

        return articles

    async def fetch(self) -> list[Article]:
        all_articles = []

        for blog in self.config.blogs:
            if blog.rss:
                posts = await self._fetch_via_rss(blog.name, blog.rss)
            else:
                posts = await self._fetch_via_html(blog.name, blog.url)
            all_articles.extend(posts)

        return all_articles
