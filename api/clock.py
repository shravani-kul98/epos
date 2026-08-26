"""UTC reporting date at the application boundary."""

from datetime import UTC, date, datetime


def utc_today() -> date:
    """Return today's reporting date without changing deterministic engine inputs."""
    return datetime.now(UTC).date()
