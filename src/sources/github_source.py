"""GitHub data source: trending repos + organization releases."""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from src.config import get_config
from src.database import Article
from src.sources.base import BaseCrawler

logger = logging.getLogger(__name__)


class GitHubCrawler(BaseCrawler):
    source_name = "github"

    # GitHub API allows 5000 req/hour with token, 60/hour without.
    # Use 0.5s between requests to stay well within limits.
    request_delay = 0.5

    def __init__(self) -> None:
        super().__init__()
        self.config = get_config().sources.github
        self.token = os.getenv("GITHUB_TOKEN")

    async def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    async def _fetch_trending_repos(self) -> list[Article]:
        """Fetch trending AI-related repositories (created/pushed recently, high stars)."""
        articles = []
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        for topic in self.config.topics:
            try:
                resp = await self.throttled_get(
                    "https://api.github.com/search/repositories",
                    params={
                        "q": f"topic:{topic} pushed:>{since}",
                        "sort": "stars",
                        "order": "desc",
                        "per_page": 10,
                    },
                    headers=await self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()

                for repo in data.get("items", []):
                    articles.append(
                        Article(
                            source=self.source_name,
                            source_id=f"repo-{repo['id']}",
                            title=f"[GitHub Trending] {repo['full_name']} ⭐{repo['stargazers_count']}",
                            url=repo["html_url"],
                            content=repo.get("description", ""),
                            category="trending_repo",
                            author=repo["owner"]["login"],
                            tags=",".join(repo.get("topics", [])[:5]),
                            extra_data=json.dumps(
                                {
                                    "stars": repo["stargazers_count"],
                                    "forks": repo["forks_count"],
                                    "language": repo.get("language"),
                                }
                            ),
                            published_at=datetime.fromisoformat(
                                repo["created_at"].replace("Z", "+00:00")
                            ),
                            fetched_at=self.now_utc(),
                        )
                    )
            except Exception as e:
                logger.warning(f"[github] Failed to fetch trending for topic={topic}: {e}")

        return articles

    async def _fetch_org_releases(self) -> list[Article]:
        """Fetch recent releases from tracked AI organizations."""
        articles = []

        for org in self.config.orgs:
            try:
                # Get recent repos from org
                resp = await self.throttled_get(
                    f"https://api.github.com/orgs/{org}/repos",
                    params={"sort": "updated", "per_page": 10},
                    headers=await self._headers(),
                )
                resp.raise_for_status()
                repos = resp.json()

                for repo in repos:
                    repo_name = repo["full_name"]
                    try:
                        rel_resp = await self.throttled_get(
                            f"https://api.github.com/repos/{repo_name}/releases",
                            params={"per_page": 3},
                            headers=await self._headers(),
                        )
                        if rel_resp.status_code != 200:
                            continue
                        releases = rel_resp.json()

                        for release in releases:
                            pub_date = release.get("published_at")
                            if pub_date:
                                pub_dt = datetime.fromisoformat(
                                    pub_date.replace("Z", "+00:00")
                                )
                                # Only include releases from the last 7 days
                                if pub_dt < datetime.now(timezone.utc) - timedelta(days=7):
                                    continue

                            articles.append(
                                Article(
                                    source=self.source_name,
                                    source_id=f"release-{release['id']}",
                                    title=f"[GitHub Release] {repo_name} {release['tag_name']}",
                                    url=release["html_url"],
                                    content=(release.get("body") or "")[:2000],
                                    category="release",
                                    author=org,
                                    tags=repo_name,
                                    published_at=pub_dt if pub_date else None,
                                    fetched_at=self.now_utc(),
                                )
                            )
                    except Exception as e:
                        logger.debug(f"[github] No releases for {repo_name}: {e}")

            except Exception as e:
                logger.warning(f"[github] Failed to fetch repos for org={org}: {e}")

        return articles

    async def fetch(self) -> list[Article]:
        trending = await self._fetch_trending_repos()
        releases = await self._fetch_org_releases()
        return trending + releases
