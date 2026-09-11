"""Consistent task progress transitions without inventing actual work dates."""

from datetime import date
from typing import Final

from src.schemas import DeliveryTask
from src.scoring_rules import StatusDomain, normalize_status

_PROGRESS_FIELDS = frozenset({"status", "completion_percent", "is_blocked"})

# Optional review of reported completion. Reported completion and accepted completion differ.
REVIEW_PENDING: Final[str] = "Pending review"
REVIEW_ACCEPTED: Final[str] = "Accepted"
REVIEW_RETURNED: Final[str] = "Returned"


def prepare_task_progress(
    task: DeliveryTask,
    previous: DeliveryTask | None,
    changed_fields: set[str],
    updated_on: date,
) -> dict[str, object]:
    """Normalize a user-requested progress change and record its reporting date."""
    result: dict[str, object] = {"last_updated_date": updated_on}
    if previous is not None and not changed_fields.intersection(_PROGRESS_FIELDS):
        return result
    state = normalize_status(task.status, StatusDomain.SCHEDULE)
    if state is None:
        raise ValueError("Choose a supported task status.")
    progress = task.completion_percent
    blocked = task.is_blocked
    was_complete = (
        previous is not None
        and normalize_status(previous.status, StatusDomain.SCHEDULE) == "Complete"
    )
    if was_complete and "status" in changed_fields and state != "Complete":
        if "completion_percent" not in changed_fields and progress == 100:
            progress = 0
        result["actual_end_date"] = None
    elif was_complete and "completion_percent" in changed_fields and progress < 100:
        if "status" not in changed_fields:
            state = "Not Started" if progress == 0 else "In Progress"
            result["actual_end_date"] = None
    if (
        "completion_percent" in changed_fields
        and progress == 100
        and "status" not in changed_fields
    ):
        state = "Complete"
    if state == "Complete":
        progress, blocked = 100, False
    elif state in {"Closed", "Cancelled"}:
        blocked = False
    else:
        if progress == 100:
            raise ValueError("Use Complete for finished work, or set progress below 100%.")
        if state == "Not Started" and progress > 0:
            state = "In Progress"
        if "status" in changed_fields:
            blocked = state == "Blocked"
        elif "is_blocked" in changed_fields and blocked:
            state = "Blocked"
    result.update(status=state, completion_percent=progress, is_blocked=blocked)
    return result
