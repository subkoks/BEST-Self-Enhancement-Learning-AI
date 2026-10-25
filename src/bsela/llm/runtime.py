"""One lock and deadline for every model-consuming command."""

from __future__ import annotations

import fcntl
import time
from collections.abc import Iterator
from contextlib import contextmanager

from bsela.memory.store import bsela_home


class ProviderError(RuntimeError):
    """Safe operator-facing failure; never contains a raw provider response."""


@contextmanager
def model_run() -> Iterator[None]:
    home = bsela_home()
    home.mkdir(parents=True, exist_ok=True)
    with (home / "processing.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProviderError("overlap: another model job is running; skipped") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def stage_timeout(deadline: float, *, max_seconds: float = 180.0) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProviderError("run deadline exceeded (20 minutes)")
    return min(max_seconds, remaining)
