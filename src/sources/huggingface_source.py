"""HuggingFace data source: trending models, papers, and spaces."""

import json
import logging
import os
from datetime import datetime, timezone

from src.database import Article
from src.sources.base import BaseCrawler

logger = logging.getLogger(__name__)


class HuggingFaceCrawler(BaseCrawler):
    source_name = "huggingface"

    def __init__(self) -> None:
        super().__init__()
        self.token = os.getenv("HF_TOKEN")

    # 1.5s between HuggingFace API calls
    request_delay = 1.5

    async def _fetch_trending_models(self) -> list[Article]:
        """Fetch trending models from HuggingFace API."""
        articles = []
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            resp = await self.throttled_get(
                "https://huggingface.co/api/models",
                params={
                    "sort": "likes",
                    "direction": -1,
                    "limit": 20,
                },
                headers=headers,
            )
            resp.raise_for_status()
            models = resp.json()

            for model in models:
                model_id = model.get("modelId") or model.get("id", "")
                articles.append(
                    Article(
                        source=self.source_name,
                        source_id=f"model-{model_id}",
                        title=f"[HF Model] {model_id}",
                        url=f"https://huggingface.co/{model_id}",
                        content=model.get("description", "")
                        or f"Pipeline: {model.get('pipeline_tag', 'N/A')}. "
                        f"Downloads: {model.get('downloads', 0)}. "
                        f"Likes: {model.get('likes', 0)}.",
                        category="model",
                        author=model_id.split("/")[0] if "/" in model_id else "",
                        tags=model.get("pipeline_tag", ""),
                        extra_data=json.dumps(
                            {
                                "downloads": model.get("downloads", 0),
                                "likes": model.get("likes", 0),
                                "pipeline_tag": model.get("pipeline_tag"),
                            }
                        ),
                        fetched_at=self.now_utc(),
                    )
                )
        except Exception as e:
            logger.warning(f"[huggingface] Failed to fetch trending models: {e}")

        return articles

    async def _fetch_trending_papers(self) -> list[Article]:
        """Fetch trending papers from HuggingFace daily papers."""
        articles = []

        try:
            resp = await self.throttled_get("https://huggingface.co/api/daily_papers")
            resp.raise_for_status()
            papers = resp.json()

            for paper in papers[:20]:
                paper_data = paper.get("paper", {})
                paper_id = paper_data.get("id", "")
                title = paper_data.get("title", "Unknown")
                summary = paper_data.get("summary", "")

                pub_date = paper_data.get("publishedAt")
                pub_dt = None
                if pub_date:
                    try:
                        pub_dt = datetime.fromisoformat(
                            pub_date.replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass

                articles.append(
                    Article(
                        source=self.source_name,
                        source_id=f"paper-{paper_id}",
                        title=f"[HF Paper] {title}",
                        url=f"https://huggingface.co/papers/{paper_id}",
                        content=summary[:2000],
                        category="paper",
                        author=", ".join(
                            a.get("name", "") for a in paper_data.get("authors", [])[:3]
                        ),
                        tags="paper",
                        extra_data=json.dumps(
                            {"upvotes": paper.get("numUpvotes", 0)}
                        ),
                        published_at=pub_dt,
                        fetched_at=self.now_utc(),
                    )
                )
        except Exception as e:
            logger.warning(f"[huggingface] Failed to fetch trending papers: {e}")

        return articles

    async def _fetch_trending_spaces(self) -> list[Article]:
        """Fetch trending Spaces from HuggingFace."""
        articles = []

        try:
            resp = await self.throttled_get(
                "https://huggingface.co/api/spaces",
                params={"sort": "likes", "direction": -1, "limit": 10},
            )
            resp.raise_for_status()
            spaces = resp.json()

            for space in spaces:
                space_id = space.get("id", "")
                articles.append(
                    Article(
                        source=self.source_name,
                        source_id=f"space-{space_id}",
                        title=f"[HF Space] {space_id}",
                        url=f"https://huggingface.co/spaces/{space_id}",
                        content=space.get("description", "")
                        or f"SDK: {space.get('sdk', 'N/A')}. "
                        f"Likes: {space.get('likes', 0)}.",
                        category="space",
                        author=space_id.split("/")[0] if "/" in space_id else "",
                        tags="space",
                        extra_data=json.dumps(
                            {"likes": space.get("likes", 0), "sdk": space.get("sdk")}
                        ),
                        fetched_at=self.now_utc(),
                    )
                )
        except Exception as e:
            logger.warning(f"[huggingface] Failed to fetch trending spaces: {e}")

        return articles

    async def fetch(self) -> list[Article]:
        models = await self._fetch_trending_models()
        papers = await self._fetch_trending_papers()
        spaces = await self._fetch_trending_spaces()
        return models + papers + spaces
