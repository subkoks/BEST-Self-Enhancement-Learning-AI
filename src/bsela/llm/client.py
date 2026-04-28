"""LLM client abstraction: Anthropic + OpenRouter live clients + in-memory fake.

Provider selection (``make_llm_client``):
    1. ``OPENROUTER_API_KEY`` set → ``OpenRouterClient`` (free tier available).
    2. ``ANTHROPIC_API_KEY`` set → ``AnthropicClient``.
    3. Neither set → raises ``RuntimeError`` with a clear message.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from bsela.llm.types import DistillResponse, JudgeVerdict
from bsela.utils.config import load_models

if TYPE_CHECKING:  # pragma: no cover
    from anthropic import Anthropic


class LLMClient(Protocol):
    """Minimal surface used by the distiller. Implementations must be idempotent."""

    def judge(self, *, system: str, user: str) -> JudgeVerdict: ...
    def distill(self, *, system: str, user: str) -> DistillResponse: ...


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json_object(text: str) -> str:
    """Pull the first {...} block out of an LLM response, tolerating prose."""
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        raise ValueError("no JSON object found in LLM response")
    return match.group(0)


@dataclass
class AnthropicClient:
    """Live client that speaks the Anthropic Messages API.

    Model ids come from ``config/models.toml`` unless overridden at
    construction time. Instantiation imports the anthropic SDK lazily so
    that projects without credentials can still import ``bsela.llm``.
    """

    judge_model: str
    distiller_model: str
    judge_max_tokens: int = 512
    distiller_max_tokens: int = 4096
    api_key: str | None = None
    _client: Anthropic | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_config(cls, *, api_key: str | None = None) -> AnthropicClient:
        cfg = load_models()
        return cls(
            judge_model=cfg.judge.model,
            distiller_model=cfg.distiller.model,
            judge_max_tokens=cfg.judge.max_tokens,
            distiller_max_tokens=cfg.distiller.max_tokens,
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
        )

    def _anthropic(self) -> Any:
        if self._client is None:
            module = importlib.import_module("anthropic")
            self._client = module.Anthropic(api_key=self.api_key)
        return self._client

    def _complete(self, *, model: str, system: str, user: str, max_tokens: int) -> str:
        resp = self._anthropic().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        chunks: list[str] = []
        for block in resp.content:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                chunks.append(text)
        return "".join(chunks)

    def judge(self, *, system: str, user: str) -> JudgeVerdict:
        raw = self._complete(
            model=self.judge_model,
            system=system,
            user=user,
            max_tokens=self.judge_max_tokens,
        )
        return JudgeVerdict.model_validate_json(_extract_json_object(raw))

    def distill(self, *, system: str, user: str) -> DistillResponse:
        raw = self._complete(
            model=self.distiller_model,
            system=system,
            user=user,
            max_tokens=self.distiller_max_tokens,
        )
        return DistillResponse.model_validate_json(_extract_json_object(raw))


@dataclass
class OpenRouterClient:
    """Live client for the OpenRouter API (OpenAI-compatible, free tier available).

    Free models: ``meta-llama/llama-3.3-70b-instruct:free``,
    ``google/gemini-2.0-flash-exp:free``.  Model ids come from
    ``config/models.toml [openrouter]`` unless overridden at construction.

    Uses only stdlib (``urllib.request``) — no extra dependencies required.
    """

    judge_model: str
    distiller_model: str
    judge_max_tokens: int = 512
    distiller_max_tokens: int = 4096
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str | None = None

    @classmethod
    def from_config(cls, *, api_key: str | None = None) -> OpenRouterClient:
        cfg = load_models().openrouter
        return cls(
            judge_model=cfg.judge_model,
            distiller_model=cfg.distiller_model,
            judge_max_tokens=cfg.judge_max_tokens,
            distiller_max_tokens=cfg.distiller_max_tokens,
            base_url=cfg.base_url,
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY"),
        )

    def _complete(self, *, model: str, system: str, user: str, max_tokens: int) -> str:
        key = self.api_key
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Get a free key at https://openrouter.ai/keys"
            )
        payload = json.dumps(
            {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/subkoks/BEST-Self-Enhancement-Learning-AI",
                "X-Title": "BSELA",
            },
            method="POST",
        )
        last_exc: Exception | None = None
        for attempt in range(4):  # up to 3 retries on 429
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    body = json.loads(resp.read().decode())
                return str(body["choices"][0]["message"]["content"])
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")
                if exc.code == 429 and attempt < 3:
                    wait = 2**attempt  # 1s, 2s, 4s
                    time.sleep(wait)
                    last_exc = RuntimeError(f"OpenRouter API error {exc.code}: {detail}")
                    continue
                raise RuntimeError(f"OpenRouter API error {exc.code}: {detail}") from exc
        raise last_exc or RuntimeError("OpenRouter request failed")

    def judge(self, *, system: str, user: str) -> JudgeVerdict:
        raw = self._complete(
            model=self.judge_model,
            system=system,
            user=user,
            max_tokens=self.judge_max_tokens,
        )
        return JudgeVerdict.model_validate_json(_extract_json_object(raw))

    def distill(self, *, system: str, user: str) -> DistillResponse:
        raw = self._complete(
            model=self.distiller_model,
            system=system,
            user=user,
            max_tokens=self.distiller_max_tokens,
        )
        return DistillResponse.model_validate_json(_extract_json_object(raw))


def make_llm_client() -> AnthropicClient | OpenRouterClient:
    """Return a live LLM client based on available env vars.

    Priority: OPENROUTER_API_KEY > ANTHROPIC_API_KEY.
    Raises RuntimeError if neither is set.
    """
    if os.environ.get("OPENROUTER_API_KEY"):
        return OpenRouterClient.from_config()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClient.from_config()
    raise RuntimeError(
        "No LLM provider configured. Set OPENROUTER_API_KEY (free at openrouter.ai) "
        "or ANTHROPIC_API_KEY."
    )


@dataclass
class FakeLLMClient:
    """Deterministic in-memory client used by tests and dry-runs."""

    judge_response: JudgeVerdict
    distill_response: DistillResponse
    judge_calls: int = 0
    distill_calls: int = 0
    last_judge_user: str = ""
    last_distill_user: str = ""

    def judge(self, *, system: str, user: str) -> JudgeVerdict:
        self.judge_calls += 1
        self.last_judge_user = user
        return self.judge_response

    def distill(self, *, system: str, user: str) -> DistillResponse:
        self.distill_calls += 1
        self.last_distill_user = user
        return self.distill_response


__all__ = [
    "AnthropicClient",
    "FakeLLMClient",
    "LLMClient",
    "OpenRouterClient",
    "_extract_json_object",
    "make_llm_client",
]
