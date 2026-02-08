"""Configuration loading from config.yaml and environment variables."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
BRIEFINGS_DIR = PROJECT_ROOT / "briefings"
SITE_DIR = PROJECT_ROOT / "site"
TEMPLATES_DIR = Path(__file__).parent / "templates"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
BRIEFINGS_DIR.mkdir(exist_ok=True)
SITE_DIR.mkdir(exist_ok=True)


class SchedulerConfig(BaseModel):
    daily_briefing_time: str = "08:00"
    weekly_briefing_day: str = "monday"


class GitHubSourceConfig(BaseModel):
    enabled: bool = True
    interval_hours: int = 6
    orgs: list[str] = []
    topics: list[str] = []


class HuggingFaceSourceConfig(BaseModel):
    enabled: bool = True
    interval_hours: int = 6


class RedditSourceConfig(BaseModel):
    enabled: bool = True
    interval_hours: int = 4
    method: str = "rss"  # rss or praw
    subreddits: list[str] = ["MachineLearning", "LocalLLaMA"]
    post_limit: int = 25


class TwitterSourceConfig(BaseModel):
    enabled: bool = False
    interval_hours: int = 4
    method: str = "rsshub"
    rsshub_base: str = "https://rsshub.app"
    accounts: list[str] = []


class ArxivSourceConfig(BaseModel):
    enabled: bool = True
    interval_hours: int = 12
    categories: list[str] = ["cs.AI", "cs.CL", "cs.LG"]
    max_results: int = 30
    keywords: list[str] = []


class LeaderboardSourceConfig(BaseModel):
    enabled: bool = True
    interval_hours: int = 24


class BlogEntry(BaseModel):
    name: str
    url: str
    rss: Optional[str] = None


class WebsiteSourceConfig(BaseModel):
    enabled: bool = True
    interval_hours: int = 6
    blogs: list[BlogEntry] = []


class SourcesConfig(BaseModel):
    github: GitHubSourceConfig = GitHubSourceConfig()
    huggingface: HuggingFaceSourceConfig = HuggingFaceSourceConfig()
    reddit: RedditSourceConfig = RedditSourceConfig()
    twitter: TwitterSourceConfig = TwitterSourceConfig()
    arxiv: ArxivSourceConfig = ArxivSourceConfig()
    leaderboard: LeaderboardSourceConfig = LeaderboardSourceConfig()
    websites: WebsiteSourceConfig = WebsiteSourceConfig()


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_base: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4096
    summarize_model: str = "gpt-4o-mini"
    briefing_model: str = "gpt-4o-mini"


class PublishConfig(BaseModel):
    method: str = "rsync"
    remote_host: str = "your-server.com"
    remote_user: str = "deploy"
    remote_path: str = "/var/www/ai-news/"
    ssh_key: str = "~/.ssh/id_rsa"
    site_title: str = "AI Daily Briefing"
    site_description: str = "AI 行业每日信息聚合简报"
    site_url: str = "https://ai-news.example.com"


class AppConfig(BaseModel):
    scheduler: SchedulerConfig = SchedulerConfig()
    sources: SourcesConfig = SourcesConfig()
    llm: LLMConfig = LLMConfig()
    publish: PublishConfig = PublishConfig()


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration from YAML file, with env var overrides."""
    if config_path is None:
        config_path = str(PROJECT_ROOT / "config.yaml")

    config_data: dict[str, Any] = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

    # Override publish settings from environment
    publish = config_data.get("publish", {})
    if os.getenv("PUBLISH_REMOTE_HOST"):
        publish["remote_host"] = os.getenv("PUBLISH_REMOTE_HOST")
    if os.getenv("PUBLISH_REMOTE_USER"):
        publish["remote_user"] = os.getenv("PUBLISH_REMOTE_USER")
    if os.getenv("PUBLISH_REMOTE_PATH"):
        publish["remote_path"] = os.getenv("PUBLISH_REMOTE_PATH")
    if os.getenv("PUBLISH_SSH_KEY"):
        publish["ssh_key"] = os.getenv("PUBLISH_SSH_KEY")
    config_data["publish"] = publish

    return AppConfig(**config_data)


# Global config instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global config instance (lazy loaded)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
