"""Small wording helpers for the sentences the engines write for people to read."""

from __future__ import annotations


def count_of(count: int, singular: str, plural: str | None = None) -> str:
    """``count`` with the right noun form: "1 task", "3 tasks", "2 dependencies"."""
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural or singular + 's'}"


def joined(items: list[str]) -> str:
    """ "a", "a and b" or "a, b and c"."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" and {items[-1]}"
