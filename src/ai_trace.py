"""Privacy-safe timing trace for one Ask EPOS request.

A trace records only stage names, durations, a random correlation ID, and per-model-call metadata:
response schema name, outcome, failure kind, prompt size, and token counts. It never records the
question, evidence, model output, headers, endpoint, or credentials, so the log line is safe to
retain alongside ordinary application logs.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field

logger = logging.getLogger("epos.ai.trace")


@dataclass(frozen=True)
class ModelCall:
    """Metadata for one structured-output request. Contains no content."""

    schema: str
    status: str
    failure: str | None
    elapsed_ms: float
    prompt_chars: int
    prompt_tokens: int | None
    completion_tokens: int | None


@dataclass
class Trace:
    """Timings for one request, keyed by stage name."""

    trace_id: str
    stages_ms: dict[str, float] = field(default_factory=dict)
    model_calls: list[ModelCall] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)

    def summary(self) -> dict[str, object]:
        """Return the loggable, content-free summary of the request."""
        return {
            "trace_id": self.trace_id,
            "total_ms": round((time.perf_counter() - self.started) * 1000, 2),
            "stages_ms": {name: round(value, 2) for name, value in self.stages_ms.items()},
            "model_calls": [asdict(call) for call in self.model_calls],
        }


_current: ContextVar[Trace | None] = ContextVar("epos_ai_trace", default=None)


@contextmanager
def request_trace() -> Iterator[Trace]:
    """Open a trace for one request and log its summary when the request ends."""
    trace = Trace(trace_id=uuid.uuid4().hex[:16])
    token = _current.set(trace)
    try:
        yield trace
    finally:
        _current.reset(token)
        logger.info("ask_epos_trace %s", json.dumps(trace.summary(), sort_keys=True))


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Accumulate the duration of a named stage into the active trace, if any."""
    trace = _current.get()
    started = time.perf_counter()
    try:
        yield
    finally:
        if trace is not None:
            elapsed = (time.perf_counter() - started) * 1000
            trace.stages_ms[name] = trace.stages_ms.get(name, 0.0) + elapsed


def record_model_call(call: ModelCall) -> None:
    """Attach one model call to the active trace. A no-op outside a traced request."""
    trace = _current.get()
    if trace is not None:
        trace.model_calls.append(call)
