"""Request limits for sign-in, registration and model-backed endpoints.

By default limits live on the application instance, so each serverless instance and each test
application counts independently. With ``EPOS_RATE_LIMIT_STORE=database`` (the production
default) every instance counts in the shared database instead, so the limit holds across them.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol

from fastapi import HTTPException, Request, status
from sqlalchemy import delete
from sqlmodel import Session, col, select

from api import settings
from api.models import RateLimitEventTable

SIGN_IN_FAILURES_PER_ACCOUNT: Final[int] = 5
SIGN_IN_FAILURES_PER_CLIENT: Final[int] = 20
SIGN_IN_WINDOW_SECONDS: Final[float] = 15 * 60
REGISTRATIONS_PER_CLIENT: Final[int] = 10
REGISTRATION_WINDOW_SECONDS: Final[float] = 60 * 60
ASSISTANT_REQUESTS_PER_USER: Final[int] = 30
ASSISTANT_WINDOW_SECONDS: Final[float] = 5 * 60

# Bounds memory when many distinct clients or accounts are seen by one instance.
_MAX_TRACKED_KEYS: Final[int] = 10_000


class WindowLimit(Protocol):
    def retry_after(self, key: str, session: Session | None = None) -> int | None: ...

    def record(self, key: str, session: Session | None = None) -> None: ...

    def reset(self, key: str, session: Session | None = None) -> None: ...


@dataclass
class SlidingWindowLimit:
    """Allow at most ``limit`` recorded events per key within a rolling window."""

    limit: int
    window_seconds: float
    clock: Callable[[], float] = time.monotonic
    _events: dict[str, deque[float]] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def retry_after(self, key: str, session: Session | None = None) -> int | None:
        """Seconds until ``key`` may act again, or ``None`` while it is within its limit."""
        with self._lock:
            events = self._current(key)
            if len(events) < self.limit:
                return None
            return max(1, int(events[0] + self.window_seconds - self.clock()) + 1)

    def record(self, key: str, session: Session | None = None) -> None:
        """Count one event against ``key``."""
        with self._lock:
            self._current(key).append(self.clock())
            self._bound_memory()

    def reset(self, key: str, session: Session | None = None) -> None:
        """Forget every event recorded against ``key``."""
        with self._lock:
            self._events.pop(key, None)

    def _current(self, key: str) -> deque[float]:
        cutoff = self.clock() - self.window_seconds
        events = self._events.setdefault(key, deque())
        while events and events[0] <= cutoff:
            events.popleft()
        return events

    def _bound_memory(self) -> None:
        if len(self._events) <= _MAX_TRACKED_KEYS:
            return
        for key in [key for key, events in self._events.items() if not events]:
            del self._events[key]
        while len(self._events) > _MAX_TRACKED_KEYS:
            del self._events[next(iter(self._events))]


@dataclass
class DatabaseWindowLimit:
    """The same rolling window, counted in the shared database so every instance agrees.

    Keys are stored only as hashes, so the table never holds an address or an email.
    """

    bucket: str
    limit: int
    window_seconds: float

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def _cutoff(self) -> datetime:
        return datetime.now(UTC) - timedelta(seconds=self.window_seconds)

    def retry_after(self, key: str, session: Session | None = None) -> int | None:
        if session is None:
            raise RuntimeError("A shared limit needs a database session.")
        times = session.exec(
            select(RateLimitEventTable.occurred_at)
            .where(
                RateLimitEventTable.bucket == self.bucket,
                RateLimitEventTable.key_hash == self._hash(key),
                col(RateLimitEventTable.occurred_at) > self._cutoff(),
            )
            .order_by(col(RateLimitEventTable.occurred_at))
        ).all()
        if len(times) < self.limit:
            return None
        oldest = times[0] if times[0].tzinfo else times[0].replace(tzinfo=UTC)
        remaining = oldest + timedelta(seconds=self.window_seconds) - datetime.now(UTC)
        return max(1, int(remaining.total_seconds()) + 1)

    def record(self, key: str, session: Session | None = None) -> None:
        if session is None:
            raise RuntimeError("A shared limit needs a database session.")
        session.add(RateLimitEventTable(bucket=self.bucket, key_hash=self._hash(key)))
        session.execute(
            delete(RateLimitEventTable).where(
                col(RateLimitEventTable.bucket) == self.bucket,
                col(RateLimitEventTable.occurred_at) <= self._cutoff(),
            )
        )
        session.commit()

    def reset(self, key: str, session: Session | None = None) -> None:
        if session is None:
            raise RuntimeError("A shared limit needs a database session.")
        session.execute(
            delete(RateLimitEventTable).where(
                col(RateLimitEventTable.bucket) == self.bucket,
                col(RateLimitEventTable.key_hash) == self._hash(key),
            )
        )
        session.commit()


@dataclass
class RateLimits:
    """Every limit one application instance enforces."""

    enabled: bool
    sign_in_account: WindowLimit
    sign_in_client: WindowLimit
    registration_client: WindowLimit
    assistant_user: WindowLimit

    @classmethod
    def from_settings(cls) -> RateLimits:
        shared = settings.rate_limit_store() == settings.RATE_LIMIT_STORE_DATABASE

        def limit(bucket: str, allowance: int, window: float) -> WindowLimit:
            if shared:
                return DatabaseWindowLimit(bucket, allowance, window)
            return SlidingWindowLimit(allowance, window)

        return cls(
            enabled=settings.rate_limits_enabled(),
            sign_in_account=limit(
                "sign_in_account", SIGN_IN_FAILURES_PER_ACCOUNT, SIGN_IN_WINDOW_SECONDS
            ),
            sign_in_client=limit(
                "sign_in_client", SIGN_IN_FAILURES_PER_CLIENT, SIGN_IN_WINDOW_SECONDS
            ),
            registration_client=limit(
                "registration_client", REGISTRATIONS_PER_CLIENT, REGISTRATION_WINDOW_SECONDS
            ),
            assistant_user=limit(
                "assistant_user", ASSISTANT_REQUESTS_PER_USER, ASSISTANT_WINDOW_SECONDS
            ),
        )


def limits_for(request: Request) -> RateLimits:
    """The limits held by the application serving ``request``."""
    limits = getattr(request.app.state, "rate_limits", None)
    if limits is None:
        limits = RateLimits.from_settings()
        request.app.state.rate_limits = limits
    return limits


def client_key(request: Request) -> str:
    """The network peer as seen by this process."""
    return f"client:{request.client.host if request.client else 'unknown'}"


def too_many_requests(retry_after: int, detail: str) -> HTTPException:
    """A 429 carrying how long the caller should wait."""
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(retry_after)},
    )


def enforce(
    limit: WindowLimit,
    keys: list[str],
    detail: str,
    *,
    record: bool,
    session: Session | None = None,
) -> None:
    """Refuse when any key is over its limit; otherwise optionally count one event for each."""
    waits = [wait for key in keys if (wait := limit.retry_after(key, session)) is not None]
    if waits:
        raise too_many_requests(max(waits), detail)
    if record:
        for key in keys:
            limit.record(key, session)
