"""Leaderboard data source: LMSYS Chatbot Arena + Open LLM Leaderboard."""

import json
import logging
from datetime import datetime, timezone

from src.database import Article
from src.sources.base import BaseCrawler

logger = logging.getLogger(__name__)


class LeaderboardCrawler(BaseCrawler):
    source_name = "leaderboard"

    async def _fetch_lmsys_arena(self) -> list[Article]:
        """Fetch LMSYS Chatbot Arena leaderboard data."""
        client = await self.get_client()
        articles = []

        try:
            # LMSYS publishes leaderboard data via their API
            resp = await client.get(
                "https://huggingface.co/api/spaces/lmsys/chatbot-arena-leaderboard",
                timeout=20.0,
            )
            if resp.status_code == 200:
                articles.append(
                    Article(
                        source=self.source_name,
                        source_id=f"lmsys-arena-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                        title="[Leaderboard] LMSYS Chatbot Arena - Daily Snapshot",
                        url="https://huggingface.co/spaces/lmsys/chatbot-arena-leaderboard",
                        content="LMSYS Chatbot Arena leaderboard snapshot. "
                        "Visit the link for the latest rankings.",
                        category="leaderboard",
                        tags="lmsys,arena,leaderboard",
                        fetched_at=self.now_utc(),
                    )
                )
        except Exception as e:
            logger.warning(f"[leaderboard] Failed to fetch LMSYS Arena: {e}")

        return articles

    async def _fetch_open_llm_leaderboard(self) -> list[Article]:
        """Fetch Open LLM Leaderboard from HuggingFace."""
        client = await self.get_client()
        articles = []

        try:
            # Try to get the leaderboard data from the HF API
            resp = await client.get(
                "https://huggingface.co/api/spaces/open-llm-leaderboard/open_llm_leaderboard",
                timeout=20.0,
            )
            if resp.status_code == 200:
                articles.append(
                    Article(
                        source=self.source_name,
                        source_id=f"open-llm-lb-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                        title="[Leaderboard] Open LLM Leaderboard - Daily Snapshot",
                        url="https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard",
                        content="Open LLM Leaderboard snapshot. "
                        "Visit the link for the latest benchmark results.",
                        category="leaderboard",
                        tags="open-llm,leaderboard,benchmark",
                        fetched_at=self.now_utc(),
                    )
                )
        except Exception as e:
            logger.warning(f"[leaderboard] Failed to fetch Open LLM Leaderboard: {e}")

        return articles

    async def _fetch_livebench(self) -> list[Article]:
        """Fetch LiveBench leaderboard."""
        client = await self.get_client()
        articles = []

        try:
            resp = await client.get("https://livebench.ai/", timeout=20.0)
            if resp.status_code == 200:
                articles.append(
                    Article(
                        source=self.source_name,
                        source_id=f"livebench-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                        title="[Leaderboard] LiveBench - Daily Snapshot",
                        url="https://livebench.ai/",
                        content="LiveBench leaderboard snapshot. "
                        "Visit the link for the latest results.",
                        category="leaderboard",
                        tags="livebench,leaderboard,benchmark",
                        fetched_at=self.now_utc(),
                    )
                )
        except Exception as e:
            logger.warning(f"[leaderboard] Failed to fetch LiveBench: {e}")

        return articles

    async def fetch(self) -> list[Article]:
        arena = await self._fetch_lmsys_arena()
        open_llm = await self._fetch_open_llm_leaderboard()
        livebench = await self._fetch_livebench()
        return arena + open_llm + livebench
