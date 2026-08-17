"""Load conductor / perspective system prompts."""

from __future__ import annotations

from interview_mux.config import repo_root

CONDUCTOR = "docs/prompts/homunculus/conductor/system.txt"


def load_conductor_system(runtime: str = "openai") -> str:
    if runtime == "mlx":
        mlx = repo_root() / "docs/prompts/homunculus/conductor/mlx.system.txt"
        if mlx.is_file():
            return mlx.read_text(encoding="utf-8")
    path = repo_root() / CONDUCTOR
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return (
        "You are the mastering homunculus. Select tools. Admit every output. "
        "Pack volleys by fact IDs only. Cite docs. Do not invent dialogue. "
        "Tape-only packets. Hard limits: max 3 per function, one analysis per issue."
    )


def load_module(rel: str) -> str:
    path = repo_root() / rel
    return path.read_text(encoding="utf-8") if path.is_file() else ""
