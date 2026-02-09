"""Database models and session management using SQLAlchemy + SQLite."""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import DATA_DIR


DATABASE_URL = f"sqlite:///{DATA_DIR / 'news.db'}"


class Base(DeclarativeBase):
    pass


class Article(Base):
    """Stores individual fetched information items from all sources."""

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False, index=True)  # github, hf, reddit, ...
    source_id = Column(String(255), nullable=True)  # unique ID within the source
    title = Column(String(500), nullable=False)
    ai_title = Column(String(500), nullable=True)  # AI-generated Chinese headline
    ai_title_en = Column(String(500), nullable=True)  # AI-generated English headline
    url = Column(String(1000), nullable=True)
    content = Column(Text, nullable=True)  # raw content / description
    summary = Column(Text, nullable=True)  # AI-generated summary (Chinese)
    summary_en = Column(Text, nullable=True)  # AI-generated summary (English)
    category = Column(String(100), nullable=True)  # model_release, paper, news, ...
    importance_score = Column(Float, nullable=True)  # 1-5 AI-rated importance
    author = Column(String(255), nullable=True)
    tags = Column(Text, nullable=True)  # comma-separated tags
    extra_data = Column(Text, nullable=True)  # JSON string for source-specific data
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ignored = Column(Integer, default=0)  # 0 = not judged/selected, 1 = judged as not important
    summarized = Column(Integer, default=0)  # 0 = not summarized, 1 = summarized

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, source={self.source}, title={self.title[:40]})>"


class Briefing(Base):
    """Stores generated daily/weekly briefings."""

    __tablename__ = "briefings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    period = Column(String(10), nullable=False)  # daily / weekly
    title = Column(String(500), nullable=False)
    title_en = Column(String(500), nullable=True)  # English title
    content_markdown = Column(Text, nullable=False)
    content_markdown_en = Column(Text, nullable=True)  # English briefing content
    content_html = Column(Text, nullable=True)
    article_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<Briefing(id={self.id}, date={self.date}, period={self.period})>"


class SourceStatus(Base):
    """Tracks the operational status of each data source crawler."""

    __tablename__ = "source_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(50), nullable=False, unique=True, index=True)
    last_run = Column(DateTime, nullable=True)
    last_success = Column(DateTime, nullable=True)
    status = Column(String(20), default="idle")  # idle, running, success, error
    error_message = Column(Text, nullable=True)
    articles_fetched = Column(Integer, default=0)  # count from last run
    total_articles = Column(Integer, default=0)  # total count ever fetched

    def __repr__(self) -> str:
        return f"<SourceStatus(source={self.source_name}, status={self.status})>"


# Engine and session factory
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """Create all tables if they don't exist, and run lightweight migrations."""
    Base.metadata.create_all(engine)
    _run_migrations()


def _run_migrations() -> None:
    """Add new columns to existing tables (safe to re-run)."""
    import sqlite3

    db_path = str(DATA_DIR / "news.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- Articles table migrations ---
    cursor.execute("PRAGMA table_info(articles)")
    article_cols = {row[1] for row in cursor.fetchall()}

    if "ai_title" not in article_cols:
        cursor.execute("ALTER TABLE articles ADD COLUMN ai_title VARCHAR(500)")
    if "ai_title_en" not in article_cols:
        cursor.execute("ALTER TABLE articles ADD COLUMN ai_title_en VARCHAR(500)")
    if "summary_en" not in article_cols:
        cursor.execute("ALTER TABLE articles ADD COLUMN summary_en TEXT")
    if "summarized" not in article_cols:
        cursor.execute("ALTER TABLE articles ADD COLUMN summarized INTEGER DEFAULT 0")

    # --- Briefings table migrations ---
    cursor.execute("PRAGMA table_info(briefings)")
    briefing_cols = {row[1] for row in cursor.fetchall()}

    if "title_en" not in briefing_cols:
        cursor.execute("ALTER TABLE briefings ADD COLUMN title_en VARCHAR(500)")
    if "content_markdown_en" not in briefing_cols:
        cursor.execute("ALTER TABLE briefings ADD COLUMN content_markdown_en TEXT")

    conn.commit()
    conn.close()


def get_session() -> Session:
    """Get a new database session."""
    return SessionLocal()


def article_exists(session: Session, source: str, source_id: str) -> bool:
    """Check if an article with this source + source_id already exists."""
    stmt = select(Article).where(
        Article.source == source, Article.source_id == source_id
    )
    return session.execute(stmt).first() is not None


def save_articles(session: Session, articles: list[Article]) -> int:
    """Save articles to database, skipping duplicates. Returns count of new articles."""
    new_count = 0
    for article in articles:
        if article.source_id and article_exists(
            session, article.source, article.source_id
        ):
            continue
        session.add(article)
        new_count += 1
    session.commit()
    return new_count


def update_source_status(
    session: Session,
    source_name: str,
    status: str,
    articles_fetched: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """Update or create a source status record."""
    stmt = select(SourceStatus).where(SourceStatus.source_name == source_name)
    result = session.execute(stmt).scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if result is None:
        result = SourceStatus(source_name=source_name)
        session.add(result)

    result.last_run = now
    result.status = status
    result.error_message = error_message
    result.articles_fetched = articles_fetched

    if status == "success":
        result.last_success = now
        result.total_articles = (result.total_articles or 0) + articles_fetched

    session.commit()
