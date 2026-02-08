"""LLM-based importance judgment for news articles."""

import json
import logging
from typing import Optional

from pydantic import BaseModel
from src.config import get_config
from src.database import Article

logger = logging.getLogger(__name__)

# Your judgment criteria - modify as your preferences evolve
JUDGMENT_SYSTEM_PROMPT = """You are an expert AI news curator. Your task is to evaluate whether an article is IMPORTANT for a professional AI/LLM researcher or engineer.

## IMPORTANT if the article is about:
1. **Major model releases** - New capabilities, architecture, training techniques
2. **Research breakthroughs** - Novel approaches, SOTA improvements, fundamental insights
3. **Industry shifts** - Company strategies, funding, partnerships, market changes
4. **Practical tutorials** - actionable guides for production AI systems
5. **Open source projects** - with real utility (not random demos)
6. **Benchmark results** - meaningful performance comparisons

## NOT important (exclude):
- Show HN / Product Hunt launches without substance
- Minor updates / bug fixes
- Random personal projects
- Non-AI tech news
- Meta-discussions about AI (e.g., "I tried ChatGPT and...")
- Recruitments / job posts
- Opinion pieces without technical depth

## Output format:
Return ONLY a JSON object with:
- "important": boolean (true/false)
- "reason": brief reason for your decision
- "priority": "high" | "medium" | "low" (only if important)

## Examples:
{"important": true, "reason": "DeepSeek released a new reasoning model with 10x efficiency", "priority": "high"}
{"important": false, "reason": "Show HN: I built a chat UI for local LLMs"}
{"important": true, "reason": "Anthropic's analysis of LLM scaling laws", "priority": "medium"}
"""


class JudgmentResult(BaseModel):
    important: bool
    reason: str
    priority: Optional[str] = None


async def judge_article(article: Article, llm_provider: str = "openai") -> JudgmentResult:
    """Judge if an article is important using LLM."""
    from src.ai.llm_client import call_llm

    content = f"""
Title: {article.title}
URL: {article.url}
Source: {article.source}
Content: {article.content[:500]}...
Tags: {article.tags}
"""

    try:
        response = await call_llm(
            model="gpt-4o-mini",
            prompt=content,
            system_prompt=JUDGMENT_SYSTEM_PROMPT,
        )

        # Parse JSON response
        data = json.loads(response)
        return JudgmentResult(
            important=data.get("important", False),
            reason=data.get("reason", ""),
            priority=data.get("priority"),
        )
    except Exception as e:
        logger.warning(f"[judgment] Failed to judge article: {e}")
        # Default to important on error (fail-safe)
        return JudgmentResult(important=True, reason="Error in judgment, defaulting to include")


async def filter_articles(
    articles: list[Article], max_high: int = 10, max_medium: int = 10
) -> list[Article]:
    """Filter articles based on LLM judgment."""
    high_priority = []
    medium_priority = []

    for article in articles:
        result = await judge_article(article)

        if result.important:
            if result.priority == "high":
                high_priority.append((article, result))
            elif result.priority == "medium":
                medium_priority.append((article, result))
            else:
                medium_priority.append((article, result))

        # Log all decisions
        logger.info(
            f"[judgment] {article.source}: {'✅' if result.important else '❌'} {article.title[:50]}... | {result.reason}"
        )

    # Sort by score/time if available
    high_priority.sort(key=lambda x: x[0].published_at or x[0].fetched_at, reverse=True)
    medium_priority.sort(key=lambda x: x[0].published_at or x[0].fetched_at, reverse=True)

    # Cap the results
    selected = [a for a, _ in high_priority[:max_high]]
    selected.extend([a for a, _ in medium_priority[:max_medium]])

    logger.info(f"[judgment] Selected {len(selected)}/{len(articles)} articles")

    return selected
