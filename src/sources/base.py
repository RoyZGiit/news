"""Base crawler abstract class for all data sources."""

import abc
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.database import (
    Article,
    get_session,
    save_articles,
    update_source_status,
)

logger = logging.getLogger(__name__)


class BaseCrawler(abc.ABC):
    """Abstract base class for all data source crawlers.

    Subclasses inherit a rate-limited HTTP helper (`throttled_get`) that
    enforces a minimum interval between outgoing requests to avoid
    triggering upstream rate limits.
    """

    # Subclasses must set this
    source_name: str = ""

    # Minimum seconds between consecutive HTTP requests for this crawler.
    # Subclasses may override to use a tighter or looser limit.
    request_delay: float = 1.0

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0.0

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create an async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "AI-News-Aggregator/1.0 (https://github.com/ai-news)"
                },
            )
        return self._client

    async def throttled_get(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        """Send a GET request with automatic rate limiting.

        Waits at least ``self.request_delay`` seconds since the previous
        request before issuing a new one.
        """
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.request_delay:
            wait = self.request_delay - elapsed
            logger.debug(
                f"[{self.source_name}] rate limiter: sleeping {wait:.2f}s"
            )
            await asyncio.sleep(wait)

        client = await self.get_client()
        kwargs: dict[str, Any] = {"params": params, "headers": headers}
        if timeout is not None:
            kwargs["timeout"] = timeout

        self._last_request_time = time.monotonic()
        return await client.get(url, **kwargs)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @abc.abstractmethod
    async def fetch(self) -> list[Article]:
        """Fetch articles from the data source. Must be implemented by subclasses."""
        ...

    async def run(self) -> int:
        """Execute the crawler: fetch articles, save to DB, update status.

        Returns the number of new articles saved.
        """
        session = get_session()
        try:
            logger.info(f"[{self.source_name}] Starting crawl...")
            update_source_status(session, self.source_name, "running")

            articles = await self.fetch()
            new_count = save_articles(session, articles)

            update_source_status(
                session, self.source_name, "success", articles_fetched=new_count
            )
            logger.info(
                f"[{self.source_name}] Done. Fetched {len(articles)} articles, "
                f"{new_count} new."
            )
            return new_count

        except Exception as e:
            logger.error(f"[{self.source_name}] Error: {e}", exc_info=True)
            update_source_status(
                session, self.source_name, "error", error_message=str(e)
            )
            return 0

        finally:
            session.close()
            await self.close()

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)
