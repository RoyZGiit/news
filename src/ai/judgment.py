"""Combined judgment + translation in one pass."""

import json
import logging

logger = logging.getLogger(__name__)

PROMPT = """你是严格的AI资讯编辑。请筛选真正重要的AI/LLM新闻。

【重要标准】- 只保留以下：
1. **重大发布**：OpenAI/Anthropic/Google/Meta/DeepSeek 等头部厂商的新模型发布
2. **突破性研究**：有实际技术创新的论文（不是增量改进）
3. **行业大事件**：融资、收购、政策、重要合作
4. **实用工具**：真正广泛使用的开源项目重大更新

【严格过滤】- 以下全部标记为不重要：
- arXiv论文（除非是顶级会议/实验室的突破性工作）
- 个人项目、Show HN、小众工具
- 常规代码更新、Bug修复、版本小迭代
- 非AI内容（即使来自AI相关subreddit）
- 招聘、Meta讨论、意见观点

请判断以下标题，只输出JSON：

[
  {{"index": 0, "important": false, "reason": "原因"}},
  ...
]

只输出JSON。"""


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
                # Keep article - will be summarized later
                selected.append(article)
                reason = r.get("reason", "")
                logger.info(f"[✓] {article.title[:50]} | {reason}")
            else:
                # Mark as ignored and summarized (skip further processing)
                article.ignored = 1
                article.summarized = 1
                reason = r.get("reason", "")
                logger.info(f"[✗] {article.title[:50]} | {reason}")

        logger.info(f"Selected {len(selected)}/{len(articles)} articles")
        return selected

    except Exception as e:
        logger.warning(f"Processing failed: {e}")
        # Return all on error
        for a in articles:
            a.ai_title = a.title
        return articles
