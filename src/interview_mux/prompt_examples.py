"""Shared example-pack injection for system prompts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root

STAGE_EXAMPLE_FILES: dict[str, str] = {
    "speaker_roles": "_shared/examples/speaker-roles.examples.md",
    "content_context": "_shared/examples/content-context.examples.md",
    "content_brief_reanchor": "_shared/examples/content-brief-reanchor.examples.md",
    "boundary_detection": "_shared/examples/boundary-detection.examples.md",
    "segment_classification": "_shared/examples/segment-classification.examples.md",
    "sound_design_palettes": "_shared/examples/sound-design-palettes.examples.md",
    "missing_framing": "_shared/examples/missing-framing.examples.md",
    "optimal_questions": "_shared/examples/optimal-questions.examples.md",
    "topic_coverage_audit": "_shared/examples/topic-coverage-audit.examples.md",
    "narrative_arc_plan": "_shared/examples/narrative-arc-plan.examples.md",
    "full_master_ranking": "_shared/examples/full-master-ranking.examples.md",
    "edl_narrative_audit": "_shared/examples/edl-narrative-audit.examples.md",
    "highlight_selection": "_shared/examples/highlight-selection.examples.md",
    "transitions": "_shared/examples/transitions.examples.md",
    "sound_design_plan_flow1": "_shared/examples/sound-design-plan-flow1.examples.md",
    "sound_design_plan_flow2": "_shared/examples/sound-design-plan-flow2.examples.md",
    "sfx_prompt_craft": "_shared/examples/sfx-prompt-regression.md",
    "podcast_show_description": "_shared/examples/podcast-show-description.examples.md",
    "podcast_sfx_brief": "_shared/examples/sfx-briefs.examples.md",
    "sfx_brief": "_shared/examples/sfx-briefs.examples.md",
    "coherence_orc03": "_shared/examples/coherence-orc03.examples.md",
}

COMPACT_EXAMPLE_MAX_CHARS_BY_STAGE: dict[str, int] = {
    "content_context": 1200,
    "sfx_prompt_craft": 2500,
    "full_master_ranking": 1000,
    "sound_design_plan_flow1": 1000,
    "sound_design_plan_flow2": 900,
    "missing_framing": 900,
    "topic_coverage_audit": 900,
    "transitions": 800,
}
COMPACT_EXAMPLE_MAX_CHARS = 600


def prompt_path(*parts: str) -> Path:
    return repo_root().joinpath("docs", "prompts", *parts)


def example_char_cap(stage_or_key: str, cfg: dict[str, Any] | None = None) -> int:
    return COMPACT_EXAMPLE_MAX_CHARS_BY_STAGE.get(stage_or_key, COMPACT_EXAMPLE_MAX_CHARS)


def prompt_examples_mode(cfg: dict[str, Any] | None = None) -> str:
    analysis = (cfg or merged_config()).get("analysis") or {}
    pe = analysis.get("prompt_examples") or {}
    mode = str(pe.get("mode", "compact")).strip().lower()
    return mode if mode in ("compact", "full") else "compact"


def prompt_examples_enabled(stage_key: str, cfg: dict[str, Any] | None = None) -> bool:
    resolved = cfg if cfg is not None else merged_config()
    analysis = resolved.get("analysis") or {}
    pe = analysis.get("prompt_examples") or {}
    if pe.get("enabled") is False:
        return False
    allowed = pe.get("stages")
    if isinstance(allowed, list) and allowed:
        return stage_key in allowed
    return stage_key in STAGE_EXAMPLE_FILES


def append_examples_to_system(
    system: str,
    example_rel: str,
    *,
    stage_key: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> str:
    """Append compact or full example markdown to a system prompt."""
    path = prompt_path(*example_rel.split("/"))
    if not path.is_file():
        return system
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return system
    if prompt_examples_mode(cfg) == "full":
        block = f"## Examples (full reference)\n{text}"
    else:
        cap = example_char_cap(stage_key or "", cfg)
        clipped = text[:cap]
        if len(text) > cap:
            clipped = clipped.rsplit("\n", 1)[0] + "\n…"
        block = f"## Compact examples (reference)\n{clipped}"
    return f"{system}\n\n---\n\n{block}"


def load_compact_examples(stage_key: str, cfg: dict[str, Any] | None = None) -> str | None:
    """Stage example pack block for a stage key (compact or full)."""
    rel = STAGE_EXAMPLE_FILES.get(stage_key)
    if not rel:
        return None
    block = append_examples_to_system("", rel, stage_key=stage_key, cfg=cfg)
    return block if block else None
