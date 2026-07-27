"""Per-domain champion store — best-known artifacts for a refinement class."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

CHAMPION_DIR = "understanding/refinement_champion"


def seed_champion(
    ctx: RunContext,
    domain: str,
    paths: list[str],
    score_vector: dict[str, float] | None = None,
    *,
    source: str = "draft",
) -> dict[str, Any]:
    """Record the draft/first-pass result as the initial champion for a domain."""
    doc = {
        "domain": domain,
        "artifact_paths": list(paths),
        "score_vector": score_vector or {"clarity": 0.5, "succinctness": 0.5, "hook": 0.5},
        "source": source,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    ctx.write_json(f"{CHAMPION_DIR}/{domain}.json", doc)
    return doc


def load_champion(ctx: RunContext, domain: str) -> dict[str, Any] | None:
    rel = f"{CHAMPION_DIR}/{domain}.json"
    if not ctx.artifact_exists(rel):
        return None
    doc = ctx.read_json(rel)
    return doc if isinstance(doc, dict) else None


def promote_candidate(
    ctx: RunContext,
    domain: str,
    candidate_paths: list[str],
    score_vector: dict[str, float],
    *,
    source: str = "refinement",
) -> dict[str, Any]:
    """A candidate beat (or tied and replaced) the champion — persist it as the new champion."""
    doc = seed_champion(ctx, domain, candidate_paths, score_vector, source=source)
    ctx.log(
        f"Champion promoted for {domain} from {source}",
        level="success",
        stage=source,
        action_id="champion_promote",
        detail={"domain": domain, "score_vector": score_vector},
    )
    return doc
