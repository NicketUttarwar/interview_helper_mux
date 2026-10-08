"""Smart intro LLM — gap-to-85% nugget recovery at episode_preface position 0."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.nugget_layup import rank_open_nuggets_for_target
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.vo_line_adjudicate import adjudicate_cfg, nugget_air_coverage

INTRO_REL = "understanding/nugget_intro_compose.json"
GAP_REL = "understanding/gap_report.json"
PREFACE_LINE_ID = "vo_intro_preface"

__all__ = [
    "INTRO_REL",
    "PREFACE_LINE_ID",
    "select_gap_to_85_nuggets",
    "run_nugget_intro_compose",
    "mint_episode_preface_at_position_0",
]


def select_gap_to_85_nuggets(
    ctx: RunContext,
    gap_report: dict[str, Any],
    *,
    deferred_ids: list[str] | None = None,
    corpus: dict[str, Any] | None = None,
) -> list[str]:
    """Rank nuggets needed to reach min_nugget_air_coverage (default 85%)."""
    cfg = adjudicate_cfg()
    target_cov = float(cfg["min_nugget_air_coverage"])
    doc = corpus if isinstance(corpus, dict) else (
        ctx.read_json("understanding/nugget_corpus.json")
        if ctx.artifact_exists("understanding/nugget_corpus.json")
        else {}
    )
    coverage, aired, eligible = nugget_air_coverage(ctx, gap_report, corpus=doc)
    deferred = {str(x) for x in (deferred_ids or []) if x}
    already = aired | deferred
    if coverage >= target_cov and not deferred:
        return []

    nuggets = [n for n in ((doc or {}).get("nuggets") or []) if isinstance(n, dict)]
    ranked = rank_open_nuggets_for_target(
        "",
        nuggets,
        exclude_ids=already,
        limit=max(1, len(eligible)),
        prefer_excluded=True,
    )
    need_count = max(0, int((target_cov * max(1, len(eligible))) - len(already)))
    picked: list[str] = []
    for row in ranked:
        nid = str(row.get("nugget_id") or "")
        if nid and nid not in already:
            picked.append(nid)
            already.add(nid)
        if len(already) >= int(target_cov * max(1, len(eligible))):
            break
        if need_count and len(picked) >= need_count:
            break
    return picked


def run_nugget_intro_compose(
    ctx: RunContext,
    gap_report: dict[str, Any],
    nugget_ids: list[str],
    *,
    llm_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Flagship intro volley — one cohesive episode_preface."""
    from interview_mux.stages.analysis_stage import run_flow_llm_stage

    if not nugget_ids:
        return {}

    want = [str(x) for x in nugget_ids if x]
    captured: dict[str, Any] = {}

    def build_input(c: RunContext) -> dict[str, Any]:
        corpus = (
            c.read_json("understanding/nugget_corpus.json")
            if c.artifact_exists("understanding/nugget_corpus.json")
            else {}
        )
        nuggets = [
            n
            for n in ((corpus or {}).get("nuggets") or [])
            if isinstance(n, dict) and str(n.get("nugget_id") or "") in set(want)
        ]
        brief = (
            c.read_json("understanding/content_brief.json")
            if c.artifact_exists("understanding/content_brief.json")
            else {}
        )
        coverage, aired, eligible = nugget_air_coverage(c, gap_report, corpus=corpus if isinstance(corpus, dict) else None)
        through = None
        if c.artifact_exists("understanding/talking_points.json"):
            talking = c.read_json("understanding/talking_points.json")
            if isinstance(talking, dict) and isinstance(talking.get("through_line"), str):
                through = talking["through_line"]
        from interview_mux.vo_delivery_card import episode_card

        packet = {
            "nugget_ids": want,
            "nuggets": nuggets,
            "content_brief": brief,
            "coverage_before": round(coverage, 4),
            "eligible_nugget_count": len(eligible),
            "aired_nugget_count": len(aired),
            "word_budget": 90,
        }
        card = episode_card(brief if isinstance(brief, dict) else None, through_line=through)
        if card:
            packet["episode_card"] = card
        return packet

    def persist_intro(c: RunContext, artifacts: dict[str, Any]) -> None:
        from interview_mux.spoken_meta_lint import scrub_spoken_edit_structure

        raw = artifacts if isinstance(artifacts, dict) else {}
        # OpenAI envelope often nests payload under stage_output (exec_13167).
        payload = (
            raw.get("stage_output")
            if isinstance(raw.get("stage_output"), dict)
            else raw
        )
        sealed: dict[str, Any] = {
            "text": scrub_spoken_edit_structure(
                str(payload.get("text") or payload.get("final_text") or "").strip()
            ),
            "nugget_ids": [
                str(x) for x in (payload.get("nugget_ids") or want) if x
            ],
            "clustered_themes": [
                str(x) for x in (payload.get("clustered_themes") or []) if x
            ],
            "rationale": str(payload.get("rationale") or ""),
            "intro_nugget_recovery": bool(
                payload.get("intro_nugget_recovery", True)
            ),
        }
        if not sealed["text"] or not sealed["nugget_ids"]:
            raise ValueError(
                f"{INTRO_REL}: sealed intro missing text/nugget_ids "
                f"(keys={sorted(raw.keys())[:12]})"
            )
        captured.clear()
        captured.update(sealed)
        c.write_json(INTRO_REL, sealed, stage_key="vo_line_adjudicate")

    runner = llm_runner or run_flow_llm_stage
    with logged_step("nugget_intro_compose/llm", ctx=ctx, stage="vo_line_adjudicate"):
        try:
            try:
                runner(
                    ctx,
                    "nugget_intro_compose",
                    "vo/nugget-intro-compose.system.txt",
                    build_input,
                    persist_intro,
                    auto_complete=False,
                )
            except TypeError:
                runner(
                    ctx,
                    "nugget_intro_compose",
                    "vo/nugget-intro-compose.system.txt",
                    build_input,
                    persist_intro,
                )
        except Exception as exc:
            # Cap exhausted after a prior successful seal (or pending seal) —
            # reuse the artifact instead of stranding Part A adjudication.
            from interview_mux.homunculus.budget import LimitExhausted

            if not isinstance(exc, LimitExhausted) and "limit_exhausted" not in str(exc):
                raise
            reused = _reuse_sealed_intro(ctx)
            if reused:
                captured.clear()
                captured.update(reused)
                ctx.log(
                    "nugget_intro_compose: reusing sealed intro after limit_exhausted",
                    level="warning",
                    stage="vo_line_adjudicate",
                )
                return captured
            raise
    return captured


def _reuse_sealed_intro(ctx: RunContext) -> dict[str, Any] | None:
    """Return a schema-usable intro from committed or pending staging, else None."""
    payload: dict[str, Any] | None = None
    try:
        if ctx.artifact_exists(INTRO_REL):
            raw = ctx.read_json(INTRO_REL)
            if isinstance(raw, dict):
                payload = raw
    except Exception:
        payload = None
    if payload is None:
        try:
            from interview_mux.write_staging import staged_path

            staged = staged_path(ctx, INTRO_REL, stage_id="vo_line_adjudicate")
            if staged.is_file():
                import json

                raw = json.loads(staged.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    payload = raw
        except Exception:
            payload = None
    if not isinstance(payload, dict):
        return None
    # Unwrap stage_output envelope if present.
    if "text" not in payload and isinstance(payload.get("stage_output"), dict):
        payload = dict(payload["stage_output"])
    text = str(payload.get("text") or "").strip()
    ids = [str(x) for x in (payload.get("nugget_ids") or []) if x]
    if not text or not ids:
        return None
    return {
        "text": text,
        "nugget_ids": ids,
        "clustered_themes": list(payload.get("clustered_themes") or []),
        "rationale": str(payload.get("rationale") or ""),
        "intro_nugget_recovery": bool(payload.get("intro_nugget_recovery", True)),
    }


def mint_episode_preface_at_position_0(
    ctx: RunContext,
    gap_report: dict[str, Any],
    intro: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """3C — mint episode_preface at position 0 with intro_nugget_recovery stamp."""
    from interview_mux.spoken_meta_lint import scrub_spoken_edit_structure

    text = scrub_spoken_edit_structure(
        str(intro.get("text") or intro.get("final_text") or "").strip()
    )
    if not text:
        return gap_report, False

    nugget_ids = [str(x) for x in (intro.get("nugget_ids") or []) if x]
    ordered = (
        ctx.read_json("master/selection.json").get("ordered_segment_ids")
        if ctx.artifact_exists("master/selection.json")
        else []
    )
    first = str(ordered[0]) if ordered else str(intro.get("targets_segment_id") or "seg_001")

    lines = [dict(x) for x in (gap_report.get("interviewer_lines") or []) if isinstance(x, dict)]
    lines = [ln for ln in lines if str(ln.get("line_id") or "") != PREFACE_LINE_ID]

    delivery = "synthesize"
    try:
        from interview_mux.gap_vo_gates import resolve_gap_vo_delivery

        delivery = "synthesize" if resolve_gap_vo_delivery(ctx) == "chatterbox" else "record"
    except Exception:
        pass

    preface = {
        "line_id": PREFACE_LINE_ID,
        "gap_type": "missing_setup",
        "line_category": "episode_preface",
        "text": text,
        "targets_segment_id": first,
        "placement": "before",
        "delivery": delivery,
        "nugget_ids": nugget_ids,
        "intro_nugget_recovery": True,
        "origin": "nugget_intro_compose",
        "rationale": str(intro.get("rationale") or "Intro sink packs deferred nuggets toward coverage floor."),
        "supports_segment_ids": [first],
    }
    gap_report["interviewer_lines"] = [preface] + lines
    return gap_report, True
