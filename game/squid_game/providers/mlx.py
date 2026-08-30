"""MLX provider for Apple Silicon local inference via mlx_lm.

Uses HuggingFace mlx-community models for on-device inference without
requiring a separate server process (unlike Ollama/vLLM).

Sampling parameters (top_p, top_k, repetition_penalty) and thinking
mode (enable_thinking) are read from ProviderConfig.

Example configuration::

    provider:
      provider: mlx
      model: mlx-community/Qwen3.5-4B-4bit
      temperature: 1.0
      top_p: 0.95
      top_k: 20
      repetition_penalty: 1.5
      enable_thinking: true
"""

import logging
import re

from squid_game.providers.base import CompletionResult, LLMProvider

logger = logging.getLogger(__name__)


class MLXProvider(LLMProvider):
    """LLM provider using Apple MLX for on-device inference.

    Loads a model from HuggingFace (typically ``mlx-community/`` org)
    and runs inference directly on Apple Silicon GPU. No API key or
    server process required.

    Args:
        model: HuggingFace repo ID.
        top_p: Nucleus sampling threshold (0.0 disables).
        top_k: Top-k sampling (0 disables).
        repetition_penalty: Repetition penalty factor (0.0 or 1.0 disables).
        repetition_context_size: Recent tokens window for repetition penalty.
        enable_thinking: Control thinking mode for models that support it
            (e.g. Qwen3.5).  None = model default, True = force on,
            False = force off.
        max_retries: Unused (kept for interface consistency).
        timeout: Unused (kept for interface consistency).
    """

    def __init__(
        self,
        model: str,
        top_p: float = 0.0,
        top_k: int = 0,
        repetition_penalty: float = 0.0,
        repetition_context_size: int = 20,
        enable_thinking: bool | None = None,
        max_retries: int = 3,
        timeout: float = 120.0,
    ) -> None:
        try:
            from mlx_lm import load
        except ImportError:
            raise ImportError(
                "mlx_lm is required for the MLX provider. "
                "Install with: uv pip install 'squid-game[mlx]'"
            )

        self._model_name = model
        self._top_p = top_p
        self._top_k = top_k
        self._repetition_penalty = repetition_penalty
        self._repetition_context_size = repetition_context_size
        self._enable_thinking = enable_thinking

        logger.info("Loading MLX model: %s", model)
        self._model, self._tokenizer = load(model)
        logger.info(
            "MLX model loaded: %s (top_p=%.2f, top_k=%d, rep_penalty=%.2f, "
            "enable_thinking=%s)",
            model, top_p, top_k, repetition_penalty, enable_thinking,
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 1.0,
        max_tokens: int = 32768,
    ) -> CompletionResult:
        """Run inference on the local MLX model.

        Uses ``stream_generate`` instead of ``generate`` to obtain
        authoritative token counts and ``finish_reason`` directly from
        the generation loop, avoiding re-encoding inaccuracies.

        Args:
            messages: Chat messages with ``role`` and ``content`` keys.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Returns:
            CompletionResult with response text and token counts.
        """
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_repetition_penalty, make_sampler

        # Build chat template kwargs for thinking mode control.
        template_kwargs: dict = {
            "add_generation_prompt": True,
            "tokenize": False,
        }
        if self._enable_thinking is not None:
            template_kwargs["enable_thinking"] = self._enable_thinking

        prompt = self._tokenizer.apply_chat_template(
            messages, **template_kwargs,
        )

        sampler = make_sampler(
            temp=temperature,
            top_p=self._top_p,
            top_k=self._top_k,
        )

        logits_processors = []
        if self._repetition_penalty > 0.0 and self._repetition_penalty != 1.0:
            logits_processors.append(
                make_repetition_penalty(
                    penalty=self._repetition_penalty,
                    context_size=self._repetition_context_size,
                )
            )

        # Use stream_generate to get authoritative token counts and
        # finish_reason from the GenerationResponse object.
        response_text = ""
        prompt_tokens = 0
        gen_tokens = 0
        finish_reason = None

        try:
            for resp in stream_generate(
                self._model,
                self._tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
                logits_processors=logits_processors or None,
            ):
                response_text += resp.text
                prompt_tokens = resp.prompt_tokens
                gen_tokens = resp.generation_tokens
                finish_reason = resp.finish_reason
        except Exception as e:
            logger.error("MLX generation failed: %s", e)
            raise RuntimeError(
                f"MLX inference failed for {self._model_name}: {e}"
            ) from e

        if finish_reason == "length":
            logger.warning(
                "MLX generation hit max_tokens (%d) — output likely truncated.",
                max_tokens,
            )

        text, thinking_tokens, thinking_text = self._parse_thinking(response_text)

        return CompletionResult(
            text=text,
            input_tokens=prompt_tokens,
            output_tokens=gen_tokens,
            thinking_tokens=thinking_tokens,
            thinking_text=thinking_text,
            logprobs=None,
            finish_reason=finish_reason,
        )

    def _parse_thinking(self, text: str) -> tuple[str, int, str | None]:
        """Extract thinking content from model output.

        Supports multiple formats:

        Qwen3 / DeepSeek:
        1. ``<think>content</think>answer`` — standard.
        2. ``content</think>answer`` — opening tag in prompt template.

        Gemma 4:
        3. ``<|channel>thought\\ncontent<channel|>answer``

        Fallback:
        4. No thinking tags — return full text with 0 thinking tokens.

        Returns:
            Tuple of (answer text, thinking token count, thinking text or None).
        """
        # --- Qwen3 / DeepSeek ---

        # Case 1: both tags present (capture all blocks)
        matches = re.findall(r"<think>(.*?)</think>", text, re.DOTALL)
        if matches:
            all_thinking = "\n".join(matches)
            thinking_tokens = len(self._tokenizer.encode(all_thinking))
            cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            return cleaned, thinking_tokens, all_thinking

        # Case 2: only </think> present (opening tag was in prompt template)
        if "</think>" in text:
            parts = text.split("</think>", 1)
            thinking_content = parts[0]
            answer = parts[1].strip() if len(parts) > 1 else ""
            thinking_tokens = len(self._tokenizer.encode(thinking_content))
            return answer, thinking_tokens, thinking_content

        # --- Gemma 4 ---

        # Case 3: <|channel>thought\n...<channel|>
        gemma_matches = re.findall(
            r"<\|channel>thought\n(.*?)<channel\|>", text, re.DOTALL,
        )
        if gemma_matches:
            all_thinking = "\n".join(gemma_matches)
            thinking_tokens = len(self._tokenizer.encode(all_thinking))
            cleaned = re.sub(
                r"<\|channel>thought\n.*?<channel\|>", "", text, re.DOTALL,
            ).strip()
            return cleaned, thinking_tokens, all_thinking

        return text, 0, None
