"""Property-based tests using Hypothesis for core pure functions."""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from bsela.core.detector import _fingerprint
from bsela.llm.distiller import _jaccard, _tokens

# ---- _jaccard properties ----


@given(st.frozensets(st.text(min_size=1, max_size=20)))
def test_jaccard_reflexive(s: frozenset[str]) -> None:
    """J(A, A) == 1.0 for any non-empty set; J(∅, ∅) == 1.0 by convention."""
    assert _jaccard(s, s) == 1.0


@given(
    st.frozensets(st.text(min_size=1, max_size=10)),
    st.frozensets(st.text(min_size=1, max_size=10)),
)
def test_jaccard_symmetric(a: frozenset[str], b: frozenset[str]) -> None:
    """J(A, B) == J(B, A) — order must not matter."""
    assert _jaccard(a, b) == _jaccard(b, a)


@given(
    st.frozensets(st.text(min_size=1, max_size=10)),
    st.frozensets(st.text(min_size=1, max_size=10)),
)
def test_jaccard_bounded(a: frozenset[str], b: frozenset[str]) -> None:
    """J(A, B) is always in [0.0, 1.0]."""
    result = _jaccard(a, b)
    assert 0.0 <= result <= 1.0


@given(
    st.frozensets(st.text(min_size=1), min_size=1),
    st.frozensets(st.text(min_size=1), min_size=1),
)
def test_jaccard_disjoint_is_zero(a: frozenset[str], b: frozenset[str]) -> None:
    """Completely disjoint sets → J == 0.0."""
    assume(not (a & b))  # skip if they happen to share an element
    assert _jaccard(a, b) == 0.0


# ---- _tokens properties ----


@given(st.text())
def test_tokens_idempotent(text: str) -> None:
    """Calling _tokens twice on the same text produces the same frozenset."""
    assert _tokens(text) == _tokens(text)


@given(st.text())
def test_tokens_all_lowercase(text: str) -> None:
    """Every token produced by _tokens is already lowercase."""
    for tok in _tokens(text):
        assert tok == tok.lower()


@given(st.text())
def test_tokens_min_length(text: str) -> None:
    """Every token is longer than 2 characters (stop-word / length filter)."""
    for tok in _tokens(text):
        assert len(tok) > 2


@given(st.text(), st.text())
def test_tokens_union_subset(a: str, b: str) -> None:
    """Tokens of (A + B) text contains at least the tokens of A alone."""
    combined = _tokens(a + " " + b)
    individual = _tokens(a)
    # individual tokens are a subset of combined (new text can only add tokens)
    assert individual <= combined


# ---- _fingerprint properties ----


@given(st.text(min_size=0, max_size=100), st.text(min_size=0, max_size=100))
@settings(max_examples=200)
def test_fingerprint_deterministic(name: str, input_text: str) -> None:
    """Same event always produces the same fingerprint (no randomness)."""
    event = {"name": name, "input": input_text}
    assert _fingerprint(event) == _fingerprint(event)


@given(st.text(min_size=0, max_size=100), st.text(min_size=0, max_size=100))
def test_fingerprint_is_40char_hex(name: str, input_text: str) -> None:
    """_fingerprint always returns a 40-character hex string (SHA-1)."""
    fp = _fingerprint({"name": name, "input": input_text})
    assert len(fp) == 40
    assert all(c in "0123456789abcdef" for c in fp)
