"""Legacy holistic fabrication stubs — disabled in v2."""

from __future__ import annotations

from typing import Any


def holistic_fabrication_enabled(*_args: Any, **_kwargs: Any) -> bool:
    return False


def should_accept_holistic_fabrication(*_args: Any, **_kwargs: Any) -> bool:
    return False


def try_holistic_fabrication_from_staged(*_args: Any, **_kwargs: Any) -> bool:
    return False
