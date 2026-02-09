"""Fast batch importance judgment by title only."""

import json
import logging

from src.config import get_config

logger = logging.getLogger(__name__)


async def batch_judge_titles(articles: list) -> list:
    """Batch judge articles by title only (fast)."""
    from src.ai.llm_client import call_llm

    if not articles:
        return []

    # Build title list
    titles = "\n".join([f'{i}. {a.title[:150]}' for i, a in enumerate(articles)])
    prompt = "你是一位专业的AI研究员。请从以下标题中筛选出 **重要** 的AI/LLM相关资讯。\n\n标题列表：\n" + titles + "\n\n判断标准：\n- 重要：主要模型发布、研究突破、行业动态、实用教程、重要基准\n- 不重要：个人项目、Show HN、招聘、非AI内容、Meta讨论\n\n输出格式（JSON数组）：\n[{\"index\": 0, \"important\": true, \"reason\": \"原因\"}, ...]"

    try:
        response = await call_llm(
            model="gpt-4o-mini",
            prompt=prompt,
        )

        # Handle JSON wrapped in code blocks
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            json_start = 0
            json_end = len(lines)
            for i, line in enumerate(lines):
                if line.startswith("{") or line.startswith("["):
                    json_start = i
                    break
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].endswith("}") or lines[i].endswith("]"):
                    json_end = i + 1
                    break
            text = "\n".join(lines[json_start:json_end])

        # Parse JSON response
        results = json.loads(text)
        return results

    except Exception as e:
        logger.warning(f"[judgment] Batch judgment failed: {e}")
        # Default all to important on error
        return [{"index": i, "important": True, "reason": "Error, default to include"} for i in range(len(articles))]


async def filter_articles(articles: list, max_high: int = 10, max_medium: int = 10) -> list:
    """Fast filter articles by title only."""
    if not articles:
        return []

    logger.info(f"[judgment] Batch judging {len(articles)} articles by title...")

    results = await batch_judge_titles(articles)

    high_priority = []
    medium_priority = []

    for result in results:
        idx = result.get("index", 0)
        if idx >= len(articles):
            continue

        article = articles[idx]
        if result.get("important", False):
            priority = result.get("priority", "medium")
            if priority == "high":
                high_priority.append(article)
            else:
                medium_priority.append(article)
        else:
            article.ignored = True
            logger.info(f"[judgment] ❌ {article.title[:50]}... | {result.get('reason', '')}")

    # Sort by published_at if available
    high_priority.sort(key=lambda x: x.published_at or x.fetched_at, reverse=True)
    medium_priority.sort(key=lambda x: x.published_at or x.fetched_at, reverse=True)

    # Cap results
    selected = high_priority[:max_high] + medium_priority[:max_medium]
    logger.info(f"[judgment] Selected {len(selected)}/{len(articles)} articles")

    return selected
