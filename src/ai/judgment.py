"""Combined judgment + translation in one pass."""

import json
import logging

logger = logging.getLogger(__name__)

PROMPT = """你是AI资讯编辑。请处理以下今日资讯标题：

{articles}

任务：
1. 判断每条是否重要（AI/LLM相关的研究、模型发布、行业动态）
2. 翻译标题为中文（简洁准确）
3. 输出JSON数组：

[
  {{"index": 0, "important": true, "title_zh": "中文标题", "summary": "一句话摘要（可选）"}},
  ...
]

只输出JSON，不要其他内容。
"""


async def process_articles(articles: list) -> list:
    """One-pass judgment + translation by title only."""
    from src.ai.llm_client import call_llm

    if not articles:
        return []

    # Build title list
    lines = "\n".join([f'{i}. [{a.source}] {a.title[:150]}' for i, a in enumerate(articles)])
    prompt = PROMPT.format(articles=lines)

    try:
        response = await call_llm(
            model="gpt-4o-mini",
            prompt=prompt,
        )

        # Handle code blocks
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

        results = json.loads(text)
        
        # Apply results
        selected = []
        for r in results:
            idx = r.get("index", 0)
            if idx >= len(articles):
                continue
            article = articles[idx]
            
            if r.get("important", False):
                # Update article with Chinese title
                article.ai_title = r.get("title_zh", article.title)
                selected.append(article)
                logger.info(f"[✓] {article.title[:50]} → {article.ai_title[:30]}")
            else:
                article.ignored = 1
                logger.info(f"[✗] {article.title[:50]} (not important)")

        logger.info(f"Selected {len(selected)}/{len(articles)} articles")
        return selected

    except Exception as e:
        logger.warning(f"Processing failed: {e}")
        # Return all on error
        for a in articles:
            a.ai_title = a.title
        return articles
