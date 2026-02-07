"""Arxiv data source: latest AI/NLP/ML papers."""

import logging
from datetime import datetime, timezone

import arxiv

from src.config import get_config
from src.database import Article
from src.sources.base import BaseCrawler

logger = logging.getLogger(__name__)


class ArxivCrawler(BaseCrawler):
    source_name = "arxiv"

    def __init__(self) -> None:
        super().__init__()
        self.config = get_config().sources.arxiv

    async def fetch(self) -> list[Article]:
        """Fetch latest papers from configured arxiv categories."""
        articles = []

        # Build search query: categories OR keywords
        cat_query = " OR ".join(f"cat:{cat}" for cat in self.config.categories)

        try:
            search = arxiv.Search(
                query=cat_query,
                max_results=self.config.max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )

            client = arxiv.Client()
            results = list(client.results(search))

            for paper in results:
                # Check if paper matches any keywords (boost relevance)
                title_lower = paper.title.lower()
                summary_lower = paper.summary.lower()
                matched_keywords = [
                    kw
                    for kw in self.config.keywords
                    if kw.lower() in title_lower or kw.lower() in summary_lower
                ]

                # Get arxiv ID
                arxiv_id = paper.entry_id.split("/abs/")[-1]

                pub_dt = paper.published
                if pub_dt and pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)

                # paper.categories is a list of strings in newer arxiv lib versions
                cat_tags = []
                for c in paper.categories[:3]:
                    cat_tags.append(c.term if hasattr(c, "term") else str(c))

                articles.append(
                    Article(
                        source=self.source_name,
                        source_id=f"arxiv-{arxiv_id}",
                        title=f"[Arxiv] {paper.title}",
                        url=paper.entry_id,
                        content=paper.summary[:2000],
                        category="paper",
                        author=", ".join(a.name for a in paper.authors[:5]),
                        tags=",".join(cat_tags + matched_keywords[:3]),
                        published_at=pub_dt,
                        fetched_at=self.now_utc(),
                    )
                )

        except Exception as e:
            logger.error(f"[arxiv] Failed to fetch papers: {e}", exc_info=True)

        return articles
