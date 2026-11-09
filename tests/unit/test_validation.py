from __future__ import annotations

import pytest

from nextstep.domain.errors import ValidationError
from nextstep.domain.validation import group_key, optional_text, required_text


def test_required_text_trims_surrounding_whitespace() -> None:
    assert required_text("  Fix login  ", "title", 200) == "Fix login"


def test_required_text_rejects_blank_value() -> None:
    with pytest.raises(ValidationError) as error:
        required_text("   ", "title", 200)
    assert error.value.field == "title"


def test_required_text_rejects_too_long_value() -> None:
    with pytest.raises(ValidationError):
        required_text("x" * 201, "title", 200)


def test_optional_text_returns_none_for_blank() -> None:
    assert optional_text("   ", "goal", 10) is None
    assert optional_text(None, "goal", 10) is None


def test_optional_text_keeps_content() -> None:
    assert optional_text("  note  ", "goal", 10) == "note"


def test_group_key_is_case_insensitive() -> None:
    assert group_key(" Work ") == group_key("work")
