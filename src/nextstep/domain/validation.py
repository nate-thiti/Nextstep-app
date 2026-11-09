"""Field-level validation and normalization rules (MVP_SPEC section 6)."""

from __future__ import annotations

from nextstep.domain.errors import ValidationError

MAX_TITLE_LENGTH = 200
MAX_GOAL_LENGTH = 10_000
MAX_GROUP_LENGTH = 100
MAX_CHECKPOINT_TEXT_LENGTH = 10_000
MAX_CONTEXT_SUMMARY_LENGTH = 20_000
MAX_REFERENCE_LABEL_LENGTH = 200
MAX_REFERENCE_TARGET_LENGTH = 4_096
MAX_SEARCH_QUERY_LENGTH = 200


def required_text(value: str | None, field: str, max_length: int) -> str:
    """Trim a required text field and enforce its length."""
    text = (value or "").strip()
    if not text:
        raise ValidationError(field, "is required")
    if len(text) > max_length:
        raise ValidationError(field, f"must be at most {max_length} characters")
    return text


def optional_text(value: str | None, field: str, max_length: int) -> str | None:
    """Trim an optional text field; blank input becomes ``None``."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > max_length:
        raise ValidationError(field, f"must be at most {max_length} characters")
    return text


def group_key(name: str) -> str:
    """Comparison key for group names; groups are case-insensitive."""
    return name.strip().casefold()
