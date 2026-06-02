"""E2E runner exceptions."""

from __future__ import annotations


class E2EError(Exception):
    """Base E2E failure."""


class E2EFailure(E2EError):
    """Job error or verification failure."""


class E2EStall(E2EError):
    """Journey state unchanged beyond timeout."""


class E2EHealExhausted(E2EError):
    """Max heal attempts reached."""
