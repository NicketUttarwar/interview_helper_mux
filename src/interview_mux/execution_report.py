"""Operator-facing execution report — written on every Full-auto terminal state."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

REPORT_JSON_REL = "operator/execution_report.json"
REPORT_MD_REL = "operator/EXECUTION_REPORT.md"

OUTCOMES = (
    "complete",
    "halted_identical_failure",
    "halted_quality",
    "halted_needs_operator",
    "incomplete_artifacts",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_info(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False, "path": str(path), "size": 0}
    return {"present": True, "path": str(path), "size": int(path.stat().st_size)}


def _cover_info(run_dir: Path) -> dict[str, Any]:
    pub = run_dir / "publish"
    for name in ("cover.jpg", "cover.png"):
        p = pub / name
        if p.is_file():
            return _file_info(p)
    return {"present": False, "path": str(pub / "cover.jpg"), "size": 0}


def _read_meta(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("run_meta.json"):
        return {}
    raw = ctx.read_json("run_meta.json")
    return raw if isinstance(raw, dict) else {}


def _g0_block(ctx: RunContext, meta: dict[str, Any]) -> dict[str, Any]:
    milestones = meta.get("journey_milestones") if isinstance(meta.get("journey_milestones"), dict) else {}
    accepted = bool(milestones.get("g0_complete") or ctx.is_done("transcript_review"))
    poison_hints: list[str] = []
    try:
        from interview_mux.artifact_completeness import compute_gaps

        if ctx.artifact_exists("understanding/speakers.json"):
            speakers = ctx.read_json("understanding/speakers.json")
            gaps = compute_gaps("understanding/speakers.json", speakers if isinstance(speakers, dict) else None)
            if any("unknown" in g.path or "role" in g.path for g in gaps):
                poison_hints.append("speakers.json role gaps — likely unreviewed STT/diarization")
        if ctx.artifact_exists("understanding/content_brief.json"):
            brief = ctx.read_json("understanding/content_brief.json")
            gaps = compute_gaps(
                "understanding/content_brief.json",
                brief if isinstance(brief, dict) else None,
            )
            if any(g.path in {"thesis", "topics"} for g in gaps):
                poison_hints.append("content_brief missing thesis/topics — transcript-poison candidate")
    except Exception:
        pass
    return {
        "accepted_unreviewed": accepted,
        "stt_poison_hints": poison_hints,
    }


def _homunculus_summary(ctx: RunContext) -> dict[str, Any]:
    try:
        from interview_mux.homunculus.issues import read_issues

        issues = read_issues(ctx)
    except Exception:
        issues = []
    kinds: dict[str, int] = {}
    for issue in issues:
        kind = str(issue.get("kind") or "unknown")
        kinds[kind] = kinds.get(kind, 0) + 1
    return {
        "issue_count": len(issues),
        "kinds": kinds,
        "recent": [
            {
                "kind": i.get("kind"),
                "stage_id": i.get("stage_id"),
                "implicated": i.get("implicated"),
            }
            for i in issues[-8:]
        ],
    }


def _identical_summary(ctx: RunContext) -> list[dict[str, Any]]:
    try:
        from interview_mux.identical_failures import read_identical_failures

        doc = read_identical_failures(ctx)
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    signatures = doc.get("signatures") or {}
    for sig in doc.get("order") or []:
        row = signatures.get(sig)
        if isinstance(row, dict):
            rows.append(
                {
                    "signature": sig,
                    "failed_stage": row.get("failed_stage"),
                    "producer": row.get("producer"),
                    "reason": row.get("reason"),
                    "count": row.get("count"),
                    "halt": row.get("halt"),
                    "resume_attempted": row.get("resume_attempted"),
                }
            )
    return rows[-40:]


def _source_profile(ctx: RunContext, meta: dict[str, Any]) -> dict[str, Any]:
    profile = str(meta.get("source_profile") or "")
    recipe = meta.get("source_profile_recipe") if isinstance(meta.get("source_profile_recipe"), dict) else {}
    extra: dict[str, Any] = {}
    dest = Path(ctx.run_dir) / "operator" / "source_profile.json"
    if dest.is_file():
        try:
            extra = ctx.read_json("operator/source_profile.json")
            if not isinstance(extra, dict):
                extra = {}
        except Exception:
            extra = {}
    return {
        "profile": profile or extra.get("profile") or "",
        "recipe": recipe or extra.get("recipe") or {},
        "duration_s": extra.get("duration_s"),
        "speaker_count": extra.get("speaker_count"),
        "noisy": extra.get("noisy"),
        "is_video": extra.get("is_video"),
    }


def _research_next(
    *,
    outcome: str,
    halt_stage: str,
    root_cause: str,
    g0: dict[str, Any],
    identical: list[dict[str, Any]],
    ship: dict[str, Any],
) -> list[str]:
    items: list[str] = []
    if g0.get("stt_poison_hints"):
        items.extend(str(x) for x in g0["stt_poison_hints"])
        items.append(
            "G0 was auto-accepted unreviewed — inspect transcript/review_queue.json for STT/domain-term errors"
        )
    halted = [r for r in identical if r.get("halt")]
    if halted:
        last = halted[-1]
        producer = last.get("producer") or last.get("failed_stage")
        items.append(
            f"Identical failure ×{last.get('count')} at {last.get('failed_stage')} "
            f"(producer={producer}): {last.get('reason')}"
        )
    if outcome != "complete":
        if halt_stage:
            items.append(f"Inspect stage {halt_stage} artifacts and completeness gaps before re-running")
        if root_cause:
            items.append(f"Root cause: {root_cause[:240]}")
    master = (ship.get("master") or {}) if isinstance(ship.get("master"), dict) else {}
    if not master.get("present"):
        items.append("master/master.wav missing — do not treat publish/S3 as a successful episode")
    cover = (ship.get("cover") or {}) if isinstance(ship.get("cover"), dict) else {}
    if master.get("present") and not cover.get("present"):
        items.append("Cover image missing — episode_cover_generate or publish package incomplete")
    if not ship.get("s3_uploaded") and outcome == "complete":
        items.append("Ship bar complete locally but S3 upload did not confirm")
    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out[:8]


def build_execution_report(
    ctx: RunContext,
    *,
    outcome: str,
    halt_stage: str = "",
    root_cause: str = "",
    decisions: list[dict[str, Any]] | None = None,
    s3: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = str(outcome or "incomplete_artifacts").strip()
    if token not in OUTCOMES:
        token = "incomplete_artifacts"
    meta = _read_meta(ctx)
    run_dir = Path(ctx.run_dir)
    master = _file_info(run_dir / "master" / "master.wav")
    cover = _cover_info(run_dir)
    audio_mp3 = _file_info(run_dir / "publish" / "audio.mp3")
    s3_info = dict(s3 or {})
    ship = {
        "master": master,
        "cover": cover,
        "publish_audio_mp3": audio_mp3,
        "publish_dir": str(run_dir / "publish"),
        "podcast_publish_done": ctx.is_done("podcast_publish"),
        "episode_cover_done": ctx.is_done("episode_cover_generate"),
        "s3_uploaded": bool(s3_info.get("uploaded") or s3_info.get("s3_uploaded")),
        "s3": s3_info,
    }
    g0 = _g0_block(ctx, meta)
    identical = _identical_summary(ctx)
    homunculus = _homunculus_summary(ctx)
    source = _source_profile(ctx, meta)
    producer = ""
    if identical:
        last = identical[-1]
        producer = str(last.get("producer") or "")
    report = {
        "version": 1,
        "written_at": _utc_now(),
        "run_id": ctx.run_id,
        "run_dir": str(run_dir),
        "outcome": token,
        "halt_stage": str(halt_stage or meta.get("needs_operator_stage") or ""),
        "root_cause": str(root_cause or meta.get("needs_operator_reason") or "")[:800],
        "producer_artifact": producer,
        "homunculus_version": str(meta.get("homunculus_version") or "0.0.0"),
        "full_auto": bool(meta.get("full_auto") or meta.get("run_mode") == "full-auto"),
        "g0": g0,
        "source_profile": source,
        "ship": ship,
        "identical_failures": identical,
        "decisions": list(decisions or [])[-80:],
        "homunculus_issues": homunculus,
        "needs_operator": bool(meta.get("needs_operator")),
        "research_next": _research_next(
            outcome=token,
            halt_stage=str(halt_stage or ""),
            root_cause=str(root_cause or ""),
            g0=g0,
            identical=identical,
            ship=ship,
        ),
    }
    if extra:
        report["extra"] = extra
    return report


def render_execution_report_md(report: dict[str, Any]) -> str:
    ship = report.get("ship") or {}
    master = ship.get("master") or {}
    cover = ship.get("cover") or {}
    mp3 = ship.get("publish_audio_mp3") or {}
    g0 = report.get("g0") or {}
    source = report.get("source_profile") or {}
    lines = [
        f"# Execution report — `{report.get('run_id')}`",
        "",
        f"- Written: {report.get('written_at')}",
        f"- Outcome: **{report.get('outcome')}**",
        f"- Homunculus: {report.get('homunculus_version')}",
        f"- Source profile: {source.get('profile') or '(none)'}",
        "",
        "## Ship bar",
        "",
        f"- Master: {'yes' if master.get('present') else 'NO'} `{master.get('path')}` ({master.get('size') or 0} bytes)",
        f"- Cover: {'yes' if cover.get('present') else 'NO'} `{cover.get('path')}`",
        f"- Publish MP3: {'yes' if mp3.get('present') else 'NO'} `{mp3.get('path')}`",
        f"- podcast_publish done: {ship.get('podcast_publish_done')}",
        f"- S3 uploaded: {ship.get('s3_uploaded')}",
        "",
        "## Halt",
        "",
        f"- Stage: `{report.get('halt_stage') or '—'}`",
        f"- Root cause: {report.get('root_cause') or '—'}",
        f"- Producer artifact: `{report.get('producer_artifact') or '—'}`",
        f"- needs_operator: {report.get('needs_operator')}",
        "",
        "## G0",
        "",
        f"- Accepted unreviewed: {g0.get('accepted_unreviewed')}",
    ]
    for hint in g0.get("stt_poison_hints") or []:
        lines.append(f"- STT poison hint: {hint}")
    lines.extend(["", "## Identical failures", ""])
    rows = report.get("identical_failures") or []
    if not rows:
        lines.append("(none)")
    else:
        for row in rows[-12:]:
            flag = " HALT" if row.get("halt") else ""
            lines.append(
                f"- `{row.get('failed_stage')}` x{row.get('count')}{flag} "
                f"producer={row.get('producer') or '—'} — {row.get('reason')}"
            )
    lines.extend(["", "## Research next", ""])
    nxt = report.get("research_next") or []
    if not nxt:
        lines.append("- None recorded.")
    else:
        for item in nxt:
            lines.append(f"- {item}")
    hom = report.get("homunculus_issues") or {}
    lines.extend(
        [
            "",
            "## Homunculus issues",
            "",
            f"- Count: {hom.get('issue_count') or 0}",
            f"- Kinds: {hom.get('kinds') or {}}",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def write_execution_report(
    ctx: RunContext,
    *,
    outcome: str,
    halt_stage: str = "",
    root_cause: str = "",
    decisions: list[dict[str, Any]] | None = None,
    s3: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_execution_report(
        ctx,
        outcome=outcome,
        halt_stage=halt_stage,
        root_cause=root_cause,
        decisions=decisions,
        s3=s3,
        extra=extra,
    )
    dest_json = Path(ctx.run_dir) / REPORT_JSON_REL
    dest_md = Path(ctx.run_dir) / REPORT_MD_REL
    dest_json.parent.mkdir(parents=True, exist_ok=True)
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(dest_json, report)
    dest_md.write_text(render_execution_report_md(report), encoding="utf-8")
    try:
        ctx.log(
            f"execution_report {outcome} → {REPORT_MD_REL}",
            level="action",
            stage=halt_stage or None,
            detail={"outcome": outcome, "md": REPORT_MD_REL, "json": REPORT_JSON_REL},
        )
    except Exception:
        pass
    return report


def stamp_needs_operator(
    ctx: RunContext,
    *,
    stage: str,
    reason: str,
    producer: str = "",
) -> None:
    def _mark(meta: dict[str, Any]) -> None:
        meta["needs_operator"] = True
        meta["needs_operator_stage"] = str(stage or "")[:80]
        meta["needs_operator_reason"] = str(reason or "")[:400]
        if producer:
            meta["needs_operator_producer"] = str(producer)[:200]

    try:
        ctx.mutate_run_meta(_mark)
    except Exception:
        pass


def report_paths(ctx: RunContext) -> tuple[Path, Path]:
    root = Path(ctx.run_dir)
    return root / REPORT_JSON_REL, root / REPORT_MD_REL


def env_is_full_auto() -> bool:
    for key in ("MUX_FULL_AUTO", "MUX_BABA_E2E", "INTERVIEW_MUX_AUTO_ACCEPT_GATES"):
        raw = str(os.environ.get(key) or "").strip().lower()
        if raw in {"1", "true", "yes"}:
            return True
    mode = str(os.environ.get("MUX_RUN_MODE") or "").strip().lower().replace("_", "-")
    return mode in {"full-auto", "fullauto", "auto", "e2e"}
