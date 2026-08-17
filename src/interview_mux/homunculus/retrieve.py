"""Retrieve top-k documentation chunks. Policy cites files, not vibes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.config import repo_root

_CANON = (
    "NORTH_STAR.md",
    "docs/INDEX.md",
    "docs/cross-cutting/mastering-homunculus.md",
    "docs/cross-cutting/mastering-process.md",
    "docs/cross-cutting/air-script.md",
    "docs/cross-cutting/llm-volley-context.md",
    "docs/workflows/operator-gates.md",
    "docs/workflows/operator-journey.md",
    "AGENTS.md",
)


def retrieve_canon(query: str, *, k: int = 5) -> dict[str, Any]:
    q = {w.lower() for w in query.split() if len(w) > 2}
    scored: list[tuple[int, str, str]] = []
    root = repo_root()
    for rel in _CANON:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        chunks = _chunk(text)
        for heading, body in chunks:
            blob = (heading + " " + body).lower()
            score = sum(1 for w in q if w in blob)
            if score:
                scored.append((score, f"{rel}#{heading}", body[:1200]))
    scored.sort(key=lambda x: -x[0])
    hits = [
        {"path": path, "excerpt": excerpt, "score": score}
        for score, path, excerpt in scored[: max(1, k)]
    ]
    if not hits:
        # Always return INDEX pointer so bootstrap packs have a cite.
        hits = [{"path": "docs/INDEX.md", "excerpt": "Documentation hub", "score": 0}]
    return {"query": query, "hits": hits}


def record_docs_cited(ctx: Any, payload: dict[str, Any]) -> None:
    """Append retrieve hits used on a decision."""
    from interview_mux.homunculus.ledger import append_ledger

    rel = "mastering/homunculus/docs_cited.jsonl"
    path = ctx.path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"query": payload.get("query"), "hits": payload.get("hits") or []}
    with path.open("a", encoding="utf-8") as fh:
        import json

        fh.write(json.dumps(row, default=str) + "\n")
    append_ledger(
        ctx,
        {
            "kind": "docs_cited",
            "identity": "retrieve_canon",
            "docs_cited": [h.get("path") for h in (payload.get("hits") or []) if isinstance(h, dict)],
        },
    )


def _chunk(text: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    heading = "intro"
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if buf:
                parts.append((heading, "\n".join(buf)))
            heading = line.lstrip("#").strip() or heading
            buf = []
        else:
            buf.append(line)
    if buf:
        parts.append((heading, "\n".join(buf)))
    return parts[:80]
