"""Shared thinking-tag parsing for server-based providers.

Extracts thinking blocks from raw LLM responses so that thinking content
is separated from the answer text.  Used by any provider that receives
inline thinking tags (MLX Server, vLLM, SGLang, etc.).

Supported formats:
    - Qwen3/DeepSeek: ``<think>...</think>``
    - Gemma 4: ``<|channel>thought\\n...<channel|>``
"""

import re

# Gemma 4 thinking tag pattern:
#   <|channel>thought\n ... <channel|>
_GEMMA4_PATTERN = re.compile(
    r"<\|channel>thought\n(.*?)<channel\|>", re.DOTALL,
)


def parse_thinking_tags(text: str) -> tuple[str, int, str | None]:
    """Extract thinking blocks from response text.

    Handles multiple formats:

    **Qwen3 / DeepSeek format:**

    1. ``<think>content</think>answer`` — standard.
    2. ``content</think>answer`` — opening tag in prompt template.

    **Gemma 4 format:**

    3. ``<|channel>thought\\ncontent<channel|>answer`` — Gemma 4 thinking.

    **Fallback:**

    4. No thinking tags — full text returned as-is.

    Token counting uses a whitespace-split heuristic (approximate).
    Providers with access to a tokenizer should override if precision
    is needed.

    Args:
        text: Raw response text potentially containing think tags.

    Returns:
        Tuple of (answer_text, thinking_token_count, thinking_text_or_None).
    """
    # --- Qwen3 / DeepSeek: <think>...</think> ---

    # Case 1: both tags present
    matches = re.findall(r"<think>(.*?)</think>", text, re.DOTALL)
    if matches:
        all_thinking = "\n".join(matches)
        thinking_tokens = len(all_thinking.split())  # approximate
        cleaned = re.sub(
            r"<think>.*?</think>", "", text, flags=re.DOTALL,
        ).strip()
        return cleaned, thinking_tokens, all_thinking

    # Case 2: only </think> present (opening tag was in prompt template)
    if "</think>" in text:
        parts = text.split("</think>", 1)
        thinking_content = parts[0]
        answer = parts[1].strip() if len(parts) > 1 else ""
        thinking_tokens = len(thinking_content.split())  # approximate
        return answer, thinking_tokens, thinking_content

    # --- Gemma 4: <|channel>thought\n...<channel|> ---

    # Case 3: Gemma 4 thinking blocks
    gemma_matches = _GEMMA4_PATTERN.findall(text)
    if gemma_matches:
        all_thinking = "\n".join(gemma_matches)
        thinking_tokens = len(all_thinking.split())
        cleaned = _GEMMA4_PATTERN.sub("", text).strip()
        return cleaned, thinking_tokens, all_thinking

    # Case 4: no thinking tags
    return text, 0, None
