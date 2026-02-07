"""Unified LLM client using LiteLLM to support multiple providers."""

import logging
from typing import Optional

import litellm

from src.config import get_config

logger = logging.getLogger(__name__)

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True


async def call_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Call an LLM via LiteLLM with unified interface.

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
        logger.error(f"LLM call failed (model={model}): {e}", exc_info=True)
        raise
