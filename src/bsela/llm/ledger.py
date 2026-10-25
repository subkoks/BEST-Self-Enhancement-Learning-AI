"""Durable attempts and conservative reservations; never stores prompt or auth."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlmodel import Field, SQLModel, select

from bsela.memory.models import _new_id, _utcnow
from bsela.memory.store import session_scope
from bsela.utils.config import load_thresholds

from .runtime import ProviderError


class LLMCall(SQLModel, table=True):
    __tablename__ = "llm_calls"

    id: str = Field(default_factory=_new_id, primary_key=True)
    run_id: str = Field(index=True)
    session_id: str = Field(index=True)
    provider: str = Field(index=True)
    model: str
    stage: str
    outcome: str = "reserved"
    billing: str  # subscription or api
    tokens_in: int = 0
    tokens_out: int = 0
    reserved_usd: float = 0.0
    cost_usd: float | None = None
    duration_ms: int = 0
    created_at: datetime = Field(default_factory=_utcnow, index=True)


def reserve(
    *,
    run_id: str,
    session_id: str,
    provider: str,
    model: str,
    stage: str,
    input_bytes: int,
    max_tokens: int,
) -> LLMCall:
    # At most one token per UTF-8 byte plus a conservative framing allowance.
    # Peak uncached input/output rates, independent of cache hits/off-peak time.
    amount = ((input_bytes + 4096) * 0.30 + max_tokens * 1.20) / 1_000_000
    paid = provider == "deepseek"
    call = LLMCall(
        run_id=run_id,
        session_id=session_id,
        provider=provider,
        model=model,
        stage=stage,
        billing="api" if paid else "subscription",
        reserved_usd=amount if paid else 0,
    )
    with session_scope() as db:
        db.exec(text("BEGIN IMMEDIATE"))  # type: ignore[call-overload]
        if paid:
            rows = list(db.exec(select(LLMCall).where(LLMCall.provider == "deepseek")).all())
            if any(row.outcome in {"reserved", "unknown"} for row in rows):
                raise ProviderError("DeepSeek has an unresolved charge; reconcile ledger first")
            policy = load_thresholds().cost
            month = datetime.now(UTC).strftime("%Y-%m")
            for limit, selected, label in (
                (
                    policy.monthly_budget_usd,
                    [r for r in rows if r.created_at.strftime("%Y-%m") == month],
                    "monthly",
                ),
                (policy.per_run_budget_usd, [r for r in rows if r.run_id == run_id], "run"),
                (
                    policy.per_session_budget_usd,
                    [r for r in rows if r.session_id == session_id],
                    "session",
                ),
            ):
                spent = sum(
                    r.cost_usd if r.cost_usd is not None else r.reserved_usd for r in selected
                )
                if spent + amount > limit + 1e-12:
                    raise ProviderError(f"DeepSeek {label} budget exceeded; no request sent")
        db.add(call)
        db.commit()
        db.refresh(call)
    return call


def finish(
    call: LLMCall,
    *,
    outcome: str,
    duration_ms: int,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float | None = None,
) -> None:
    call.outcome = outcome
    call.duration_ms = duration_ms
    call.tokens_in = tokens_in
    call.tokens_out = tokens_out
    call.cost_usd = cost_usd
    with session_scope() as db:
        db.add(call)
        db.commit()


def usage_summary(start: datetime, end: datetime) -> dict[str, int | float]:
    with session_scope() as db:
        rows = list(
            db.exec(
                select(LLMCall).where(LLMCall.created_at >= start).where(LLMCall.created_at <= end)
            ).all()
        )
    return {
        "api_cost_usd": sum(r.cost_usd or 0 for r in rows if r.billing == "api"),
        "api_reserved_usd": sum(
            r.reserved_usd for r in rows if r.billing == "api" and r.cost_usd is None
        ),
        "subscription_calls": sum(r.billing == "subscription" for r in rows),
        "subscription_tokens_in": sum(r.tokens_in for r in rows if r.billing == "subscription"),
        "subscription_tokens_out": sum(r.tokens_out for r in rows if r.billing == "subscription"),
    }


def render_usage(usage: dict[str, int | float]) -> list[str]:
    return [
        "## Model usage",
        "",
        f"- API unresolved reservations: ${usage.get('api_reserved_usd', 0):.6f}",
        f"- Codex subscription calls: {usage.get('subscription_calls', 0)}; "
        "monetary cost unmeasured",
        f"- Codex tokens: input={usage.get('subscription_tokens_in', 0)} "
        f"output={usage.get('subscription_tokens_out', 0)}",
        "",
    ]
