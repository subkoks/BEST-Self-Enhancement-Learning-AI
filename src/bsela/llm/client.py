"""LLM client abstraction: Anthropic live client + in-memory fake for tests."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

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

    def _anthropic(self) -> Anthropic:
        if self._client is None:
            from anthropic import Anthropic as _Anthropic

            self._client = _Anthropic(api_key=self.api_key)
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


def _load_json_payload(text: str) -> dict[str, object]:
    """Utility for tests that want to inspect the user payload JSON."""
    return json.loads(text)


__all__ = [
    "AnthropicClient",
    "FakeLLMClient",
    "LLMClient",
    "_extract_json_object",
    "_load_json_payload",
]
