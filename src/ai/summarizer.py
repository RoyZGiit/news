"""AI summarization engine: generates headlines, summaries, and importance scores."""

import asyncio
import json
import logging
from typing import Optional

from sqlalchemy import select

from src.ai.llm_client import call_llm
from src.config import get_config
from src.database import Article, get_session

logger = logging.getLogger(__name__)

SUMMARIZE_SYSTEM_PROMPT = """你是一个AI行业资讯编辑。你的任务是：

1. **生成中文标题**（15-30字）：提炼新闻核心信息，写一个有信息量的中文标题。
   - 好标题示例："Anthropic发布Claude 3.5 Sonnet，编程能力超越GPT-4o"
   - 好标题示例："Meta开源Llama 3.1 405B，首个可商用千亿参数模型"
   - 坏标题（太泛）："一个新的AI模型"

2. **生成英文标题**（concise, 8-15 words）：Same news summarized as an English headline.
   - Good: "Anthropic Launches Claude 3.5 Sonnet, Outperforming GPT-4o in Coding"
   - Good: "Meta Open-Sources Llama 3.1 405B, First Commercial Trillion-Param Model"
   - Bad (too vague): "A new AI model"

3. **生成中文摘要**（1-2句话）：补充标题没有覆盖的关键信息。

4. **生成英文摘要**（1-2 sentences）：Key information not covered by the English title.

5. **评估重要性**（1-5分）：
   - 5分：重大突破（新旗舰模型、行业变革性事件）
   - 4分：重要进展（知名厂商更新、重要论文、显著技术进步）
   - 3分：值得关注（有趣的开源项目、热门讨论）
   - 2分：一般信息（常规更新、小改进）
   - 1分：低价值（重复内容、低相关性）

请严格以JSON格式返回，不要有其他内容：
{"title": "中文标题", "title_en": "English Title", "summary": "中文摘要", "summary_en": "English summary", "score": 4}
"""

SUMMARIZE_USER_TEMPLATE = """来源: {source}
原始标题: {title}
内容: {content}
链接: {url}
"""


async def summarize_article(
    article: Article,
) -> tuple[str, str, str, str, float]:
    """Generate bilingual AI headlines, summaries, and importance score for an article.

    Returns:
        Tuple of (ai_title, ai_title_en, summary, summary_en, importance_score).
    """
    config = get_config().llm
    content = article.content or ""
    if len(content) > 1500:
        content = content[:1500] + "..."

    prompt = SUMMARIZE_USER_TEMPLATE.format(
        source=article.source,
        title=article.title,
        content=content,
        url=article.url or "",
    )

    try:
        response = await call_llm(
            prompt=prompt,
            system_prompt=SUMMARIZE_SYSTEM_PROMPT,
            model=config.summarize_model,
            temperature=0.2,
            max_tokens=800,
        )

        # Parse JSON response — handle markdown code blocks
        response_clean = response.strip()
        if response_clean.startswith("```"):
            lines = response_clean.split("\n")
            response_clean = "\n".join(lines[1:-1])

        data = json.loads(response_clean)
        ai_title = data.get("title", "")
        ai_title_en = data.get("title_en", "")
        summary = data.get("summary", "")
        summary_en = data.get("summary_en", "")
        score = float(data.get("score", 3))
        score = max(1.0, min(5.0, score))

        return ai_title, ai_title_en, summary, summary_en, score

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse LLM response for article {article.id}: {e}")
        return "", "", "", "", 3.0
    except Exception as e:
        logger.error(f"Summarization failed for article {article.id}: {e}")
        return "", "", "", "", 3.0


async def summarize_unsummarized(batch_size: int = 20) -> int:
    """Find and summarize articles that don't have summaries yet (skip ignored).

    Returns the number of articles summarized.
    """
    session = get_session()
    try:
        stmt = (
            select(Article)
            .where(
                (Article.summary.is_(None) | (Article.summary == ""))
                & (Article.ignored != 1)  # Skip ignored articles
            )
            .order_by(Article.fetched_at.desc())
            .limit(batch_size)
        )
        articles = session.execute(stmt).scalars().all()

        count = 0
        for article in articles:
            try:
                ai_title, ai_title_en, summary, summary_en, score = (
                    await summarize_article(article)
                )
                article.ai_title = ai_title
                article.ai_title_en = ai_title_en
                article.summary = summary
                article.summary_en = summary_en
                article.importance_score = score
                session.commit()
                count += 1
                logger.debug(
                    f"Summarized article {article.id}: score={score}, "
                    f"title={ai_title[:40]}"
                )
            except Exception as e:
                logger.warning(f"Skip summarizing article {article.id}: {e}")
                session.rollback()

            # Pause between articles to avoid hitting LLM rate limits
            await asyncio.sleep(1.0)

        logger.info(f"Summarized {count}/{len(articles)} articles.")
        return count

    finally:
        session.close()
