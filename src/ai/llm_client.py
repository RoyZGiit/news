"""Unified LLM client using LiteLLM to support multiple providers.

Includes rate limiting (minimum interval between calls) and retry with
exponential backoff for transient / rate-limit errors.
"""

import asyncio
import logging
import time
from typing import Optional

import litellm

from src.config import get_config

logger = logging.getLogger(__name__)

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True

# ---------------------------------------------------------------------------
# Module-level rate limiter — ensures a minimum gap between consecutive calls
# ---------------------------------------------------------------------------
_lock = asyncio.Lock()
_last_call_time: float = 0.0

# Minimum seconds between LLM requests (adjustable)
LLM_MIN_INTERVAL: float = 2.0

# Retry settings
LLM_MAX_RETRIES: int = 3
LLM_RETRY_BASE_DELAY: float = 5.0  # base delay in seconds (doubles each retry)


async def _wait_for_rate_limit() -> None:
    """Enforce minimum interval between LLM calls."""
    global _last_call_time
    async with _lock:
        now = time.monotonic()
        elapsed = now - _last_call_time
        if elapsed < LLM_MIN_INTERVAL:
            wait = LLM_MIN_INTERVAL - elapsed
            logger.debug(f"LLM rate limiter: sleeping {wait:.1f}s")
            await asyncio.sleep(wait)
        _last_call_time = time.monotonic()


def _is_retryable(exc: Exception) -> bool:
    """Check if the exception is a transient / rate-limit error worth retrying."""
    exc_str = str(exc).lower()
    # litellm wraps HTTP errors; look for common rate-limit indicators
    if "429" in exc_str or "rate" in exc_str or "limit" in exc_str:
        return True
    if "503" in exc_str or "502" in exc_str or "timeout" in exc_str:
        return True
    if "overloaded" in exc_str or "capacity" in exc_str:
        return True
    return False


async def call_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Call an LLM via LiteLLM with unified interface.

    Includes automatic rate limiting and retry with exponential backoff
    for transient / rate-limit errors (429, 503, timeouts, etc.).

    Args:
        prompt: The user message / prompt.
        system_prompt: Optional system message.
        model: Override model name (e.g. 'gpt-4o-mini', 'claude-3-haiku-20240307').
        temperature: Override temperature.
        max_tokens: Override max output tokens.

    Returns:
        The LLM's text response.
    """
    config = get_config().llm
    model = model or config.model
    temperature = temperature if temperature is not None else config.temperature
    max_tokens = max_tokens or config.max_tokens

    # Set API base if configured
    api_base = config.api_base

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    last_exc: Optional[Exception] = None

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        # Enforce minimum interval between calls
        await _wait_for_rate_limit()

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                api_base=api_base,
            )
            content = response.choices[0].message.content
            return content.strip() if content else ""

        except Exception as e:
            last_exc = e
            if attempt < LLM_MAX_RETRIES and _is_retryable(e):
                delay = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"LLM call failed (attempt {attempt}/{LLM_MAX_RETRIES}, "
                    f"model={model}): {e}. Retrying in {delay:.0f}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"LLM call failed (model={model}): {e}", exc_info=True)
                raise

    # Should not reach here, but just in case
    raise last_exc  # type: ignore[misc]
