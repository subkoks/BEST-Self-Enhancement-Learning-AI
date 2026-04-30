"""Unit tests for bsela.llm.client — covers OpenRouterClient, make_llm_client,
and AnthropicClient via mocked network/SDK calls.

No real HTTP requests or Anthropic SDK calls are made: urllib.request.urlopen
and importlib.import_module are patched at the boundary.
"""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from bsela.llm.client import (
    AnthropicClient,
    FakeLLMClient,
    OpenRouterClient,
    _extract_json_object,
    make_llm_client,
)
from bsela.llm.types import DistillResponse, JudgeVerdict, LessonCandidate

# ---- helpers ----


def _or_client(api_key: str = "sk-or-test") -> OpenRouterClient:
    return OpenRouterClient(
        judge_model="test/model",
        distiller_model="test/model",
        api_key=api_key,
    )


def _mock_response(body: dict) -> MagicMock:
    """Return a context-manager mock for urllib.request.urlopen."""
    raw = json.dumps(body).encode()
    resp = MagicMock()
    resp.read.return_value = raw
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _choice_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


# ---- _extract_json_object (already in test_distiller but also exercised here) ----


def test_extract_json_nested_object() -> None:
    raw = 'prefix {"key": {"nested": true}} suffix'
    assert json.loads(_extract_json_object(raw)) == {"key": {"nested": True}}


# ---- OpenRouterClient._complete ----


def test_open_router_complete_success() -> None:
    client = _or_client()
    response_body = _choice_response('{"goal_achieved": true}')
    with patch("urllib.request.urlopen", return_value=_mock_response(response_body)):
        result = client._complete(model="test/model", system="sys", user="usr", max_tokens=64)
    assert '"goal_achieved": true' in result


def test_open_router_complete_raises_without_api_key() -> None:
    client = OpenRouterClient(judge_model="m", distiller_model="m", api_key=None)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        client._complete(model="m", system="s", user="u", max_tokens=10)


def test_open_router_complete_raises_on_non_429_http_error() -> None:
    client = _or_client()
    err = urllib.error.HTTPError(
        url="https://x", code=401, msg="Unauthorized", hdrs=MagicMock(), fp=BytesIO(b"denied")
    )
    with patch("urllib.request.urlopen", side_effect=err), pytest.raises(RuntimeError, match="401"):
        client._complete(model="m", system="s", user="u", max_tokens=10)


def test_open_router_complete_retries_429_then_succeeds() -> None:
    """First call returns 429; second succeeds. time.sleep is patched out."""
    client = _or_client()
    success_resp = _mock_response(_choice_response('{"ok": 1}'))
    err_429 = urllib.error.HTTPError(
        url="https://x",
        code=429,
        msg="Too Many Requests",
        hdrs=MagicMock(),
        fp=BytesIO(b"rate limited"),
    )
    call_count = 0

    def side_effect(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise err_429
        return success_resp

    with (
        patch("urllib.request.urlopen", side_effect=side_effect),
        patch("time.sleep"),
    ):  # don't actually wait
        result = client._complete(model="m", system="s", user="u", max_tokens=10)
    assert call_count == 2
    assert '"ok": 1' in result


def test_open_router_complete_raises_after_max_retries() -> None:
    """All 4 attempts return 429 → RuntimeError."""
    client = _or_client()
    err_429 = urllib.error.HTTPError(
        url="https://x",
        code=429,
        msg="Too Many Requests",
        hdrs=MagicMock(),
        fp=BytesIO(b"rate limited"),
    )
    with (
        patch("urllib.request.urlopen", side_effect=err_429),
        patch("time.sleep"),
        pytest.raises(RuntimeError),
    ):
        client._complete(model="m", system="s", user="u", max_tokens=10)


# ---- OpenRouterClient._complete_with_json_retry ----


def test_json_retry_succeeds_on_first_json_response() -> None:
    client = _or_client()
    good_json = '{"goal_achieved": true, "confidence": 0.9}'
    with patch.object(client, "_complete", return_value=good_json) as mock_complete:
        result = client._complete_with_json_retry(model="m", system="s", user="u", max_tokens=10)
    assert result == good_json
    assert mock_complete.call_count == 1


def test_json_retry_retries_on_prose_then_returns_json() -> None:
    client = _or_client()
    prose = "Sure, here is what I think about the session."
    good_json = '{"goal_achieved": false, "confidence": 0.5}'
    responses = [prose, good_json]
    with patch.object(client, "_complete", side_effect=responses), patch("time.sleep"):
        result = client._complete_with_json_retry(model="m", system="s", user="u", max_tokens=10)
    assert result == good_json


def test_json_retry_raises_after_all_prose() -> None:
    client = _or_client()
    with (
        patch.object(client, "_complete", return_value="pure prose, no JSON"),
        patch("time.sleep"),
        pytest.raises(ValueError, match="no JSON object"),
    ):
        client._complete_with_json_retry(model="m", system="s", user="u", max_tokens=10)


# ---- OpenRouterClient.judge / distill ----


def test_open_router_judge_parses_verdict() -> None:
    client = _or_client()
    raw = json.dumps(
        {
            "goal_achieved": True,
            "efficiency": 0.9,
            "looped": False,
            "wasted_tokens": False,
            "confidence": 0.95,
            "notes": "",
        }
    )
    with patch.object(client, "_complete_with_json_retry", return_value=raw):
        verdict = client.judge(system="sys", user="usr")
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.goal_achieved is True
    assert verdict.confidence == pytest.approx(0.95)


def test_open_router_distill_parses_response() -> None:
    client = _or_client()
    raw = json.dumps(
        {
            "status": "ok",
            "confidence": 0.88,
            "lessons": [
                {
                    "rule": "Stop retrying on ENOENT",
                    "why": "waste",
                    "how_to_apply": "change strategy",
                    "scope": "project",
                    "confidence": 0.9,
                    "evidence": {},
                }
            ],
        }
    )
    with patch.object(client, "_complete_with_json_retry", return_value=raw):
        resp = client.distill(system="sys", user="usr")
    assert isinstance(resp, DistillResponse)
    assert len(resp.lessons) == 1
    assert resp.lessons[0].rule == "Stop retrying on ENOENT"


# ---- make_llm_client ----


def test_make_llm_client_prefers_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = make_llm_client()
    assert isinstance(client, OpenRouterClient)


def test_make_llm_client_falls_back_to_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    client = make_llm_client()
    assert isinstance(client, AnthropicClient)


def test_make_llm_client_raises_when_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="No LLM provider"):
        make_llm_client()


# ---- AnthropicClient.judge (mocked SDK) ----


def test_anthropic_client_judge_calls_sdk() -> None:
    client = AnthropicClient(
        judge_model="claude-haiku-4-5",
        distiller_model="claude-opus-4-7",
        api_key="sk-ant-test",
    )
    verdict_payload = json.dumps(
        {
            "goal_achieved": False,
            "efficiency": 0.3,
            "looped": True,
            "wasted_tokens": True,
            "confidence": 0.7,
            "notes": "loop detected",
        }
    )
    # Mock the anthropic SDK messages.create response
    mock_block = MagicMock()
    mock_block.text = verdict_payload
    mock_resp = MagicMock()
    mock_resp.content = [mock_block]
    mock_anthropic_module = MagicMock()
    mock_anthropic_module.Anthropic.return_value.messages.create.return_value = mock_resp

    with patch("importlib.import_module", return_value=mock_anthropic_module):
        verdict = client.judge(system="sys", user="usr")

    assert isinstance(verdict, JudgeVerdict)
    assert verdict.looped is True
    assert verdict.confidence == pytest.approx(0.7)


# ---- FakeLLMClient (already in other tests, sanity-check here) ----


def test_fake_client_increments_call_counters() -> None:
    verdict = JudgeVerdict(
        goal_achieved=True,
        efficiency=1.0,
        looped=False,
        wasted_tokens=False,
        confidence=0.99,
    )
    distill = DistillResponse(
        status="ok",
        confidence=0.9,
        lessons=[
            LessonCandidate(
                rule="test rule",
                why="why",
                how_to_apply="how",
                scope="project",
                confidence=0.9,
            )
        ],
    )
    fake = FakeLLMClient(judge_response=verdict, distill_response=distill)
    fake.judge(system="s", user="u")
    fake.judge(system="s", user="u")
    fake.distill(system="s", user="u")
    assert fake.judge_calls == 2
    assert fake.distill_calls == 1
