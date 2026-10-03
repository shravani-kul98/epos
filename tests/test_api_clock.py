"""The active application's default date follows the UTC wall clock."""

from datetime import UTC, datetime

from api.clock import utc_today
from api.dependencies import get_as_of_date


def test_live_date_is_today_not_the_fixed_demo_reference() -> None:
    before = datetime.now(UTC).date()
    current = utc_today()
    reference = get_as_of_date()
    after = datetime.now(UTC).date()
    assert before <= current <= after
    assert before <= reference <= after
