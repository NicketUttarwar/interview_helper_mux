"""Static guard: LLM-bound clip sites must use canonical truncation markers."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "interview_mux"

ALLOWLIST = {
    "llm_output_resilience.py",  # log detail cap only
    "truncation_policy.py",
}


def test_llm_clip_sites_use_markers_or_gateway():
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path.name in ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        if "truncated]" not in text and "truncation_policy" not in text:
            continue
        if "[:4000]" in text and not any(m in text for m in ("…[truncated]", "…[digest truncated]", "…[volley_middle_truncated]")):
            rel = path.relative_to(REPO)
            if "local_volley_framer" not in str(rel):
                offenders.append(f"{rel}: hard 4000 clip without digest marker")
    assert not offenders, "\n".join(offenders)
