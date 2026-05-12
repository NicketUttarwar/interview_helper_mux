from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from openai_mux.settings import load_openai_settings
from openai_mux.versions import OPENAI_PYTHON_SDK_MAJOR

if TYPE_CHECKING:
    from openai import OpenAI


def _ensure_openai_sdk_major_line() -> None:
    """Fail fast if the installed ``openai`` package is outside the pinned major line."""
    import openai as openai_pkg

    major_str = openai_pkg.__version__.split(".", 1)[0]
    try:
        major = int(major_str)
    except ValueError as e:
        raise ImportError(f"Unparseable openai package version: {openai_pkg.__version__!r}") from e
    if major != OPENAI_PYTHON_SDK_MAJOR:
        raise ImportError(
            f"openai_mux expects the openai package major version {OPENAI_PYTHON_SDK_MAJOR}.x "
            f"(see requirements-integrations.txt). Installed: {openai_pkg.__version__}."
        )


def get_openai_client(*, repo_root: Path | None = None) -> OpenAI:
    """Build a synchronous OpenAI client using repo-local or env configuration."""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise ImportError(
            "Install the OpenAI SDK: pip install -r requirements.txt "
            f"(openai {OPENAI_PYTHON_SDK_MAJOR}.x)"
        ) from e

    _ensure_openai_sdk_major_line()
    s = load_openai_settings(repo_root=repo_root)
    return OpenAI(api_key=s.api_key)
