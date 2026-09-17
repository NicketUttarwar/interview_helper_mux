"""Pipeline stages for Local Audio Probe Platform + vernacular sanitize."""

from __future__ import annotations

from typing import Any

from interview_mux.audio_probe_orchestrator import (
    build_audio_probe_artifacts,
    empty_probe_artifacts,
)
from interview_mux.config import merged_config
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.vernacular_sanitize import sanitize_manifest_with_zones


def _safe_read_json(ctx: RunContext, rel: str, *, stage: str) -> dict[str, Any] | None:
    if not ctx.artifact_exists(rel):
        return None
    try:
        doc = ctx.read_json(rel)
    except Exception as exc:  # noqa: BLE001
        ctx.log(
            f"Corrupt/unreadable artifact {rel}: {exc}",
            level="warning",
            stage=stage,
            action_id="audio_probes.artifact.corrupt",
            detail={"path": rel, "error": str(exc)[:300]},
        )
        return None
    return doc if isinstance(doc, dict) else None


def enforcement_mode_for_ctx(ctx: RunContext | None = None) -> str:
    cfg = dict((merged_config().get("audio_probes") or {}))
    mode = str(cfg.get("enforcement_mode") or "shadow")
    if ctx is not None:
        facts = _safe_read_json(ctx, "analysis/run_golden_facts.json", stage="audio_probes")
        if facts:
            run = facts.get("run") if isinstance(facts.get("run"), dict) else {}
            mode = str(run.get("enforcement_mode") or mode)
    return mode


def load_must_keep_segment_ids(ctx: RunContext) -> set[str]:
    """All vernacular must_keep ids regardless of enforcement (soft consumers / shadow)."""
    ids: set[str] = set()
    side = _safe_read_json(ctx, "analysis/vernacular_must_keep.json", stage="audio_probes")
    if side:
        for sid in side.get("must_keep_segment_ids") or []:
            if sid:
                ids.add(str(sid))
    facts = _safe_read_json(ctx, "analysis/run_golden_facts.json", stage="audio_probes")
    if facts:
        for sid in (facts.get("run") or {}).get("vernacular_must_keep_segment_ids") or []:
            if sid:
                ids.add(str(sid))
    report = _safe_read_json(ctx, "vernacular/resplit_report.json", stage="audio_probes")
    if report:
        for sid in report.get("must_keep_segment_ids") or []:
            if sid:
                ids.add(str(sid))
    return ids


def vernacular_must_keep_ids(ctx: RunContext) -> set[str]:
    """Soft advisory ids (always available when artifacts exist)."""
    return load_must_keep_segment_ids(ctx)


def authoritative_must_keep_ids(ctx: RunContext) -> set[str]:
    """Hard must_keep: vernacular (when authoritative) ∪ low-conf density top decile.

    The low-conf set carries its own ``analysis.low_conf_selection.enforcement_mode``
    so the densest STT-weak natives stay unpackable even while vernacular runs in
    shadow.
    """
    ids: set[str] = set()
    if enforcement_mode_for_ctx(ctx) == "authoritative":
        ids |= load_must_keep_segment_ids(ctx)
    try:
        from interview_mux.low_conf_islands import authoritative_low_conf_must_keep_ids

        ids |= authoritative_low_conf_must_keep_ids(ctx)
    except Exception:  # noqa: BLE001
        pass
    return ids


def run_audio_probe_build(ctx: RunContext) -> None:
    """After STT: speaker flows → probes → golden facts → protected zones."""
    stage = "audio_probe_build"
    cfg = dict((merged_config().get("audio_probes") or {}))
    fail_open = bool(cfg.get("fail_open", True))
    enforcement = str(cfg.get("enforcement_mode") or "shadow")

    if not bool(cfg.get("enabled", True)):
        arts = empty_probe_artifacts(enforcement_mode=enforcement, reason="disabled")
        ctx.write_json("analysis/run_golden_facts.json", arts["golden_facts"])
        ctx.write_json("transcript/protected_zones.json", arts["protected_zones"])
        ctx.write_json("transcript/speaker_flows.json", arts["speaker_flows"])
        ctx.write_json("vernacular/probe_report.json", arts["probe_report"])
        ctx.write_json("vernacular/audio_tags_by_flow.json", {"version": 1, "by_flow": {}})
        ctx.log(
            "audio_probe_build skipped (audio_probes.enabled=false)",
            stage=stage,
            action_id="audio_probes.build.skip",
        )
        from interview_mux.stage_completion import heal_or_raise

        heal_or_raise(ctx, stage)
        return

    ctx.artifact_exists_required(
        "transcript/full.json",
        stage=stage,
        label="Transcript from transcribe",
    )
    transcript = ctx.read_json("transcript/full.json")
    if not isinstance(transcript, dict):
        raise RuntimeError("transcript/full.json must be an object")

    source_wav = None
    if ctx.artifact_exists("ingest/normalized.wav"):
        try:
            source_wav = ctx.read_path("ingest", "normalized.wav")
        except Exception as exc:  # noqa: BLE001
            ctx.log(
                f"Could not resolve ingest/normalized.wav: {exc}",
                level="warning",
                stage=stage,
                action_id="audio_probes.source_wav.fail_open",
                detail={"error": str(exc)[:300]},
            )

    work_dir = None
    try:
        work_dir = ctx.path("vernacular", "work")
        work_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        work_dir = None

    with logged_step(f"{stage}/run_platform", ctx=ctx, stage=stage):
        try:
            arts = build_audio_probe_artifacts(
                transcript,
                ctx=ctx,
                source_wav=source_wav,
                work_dir=work_dir,
                stage=stage,
            )
        except Exception as exc:  # noqa: BLE001
            ctx.log(
                f"audio_probe_build failed: {exc}",
                level="error",
                stage=stage,
                action_id="audio_probes.build.fail",
                detail={"error": str(exc)[:500]},
            )
            if not fail_open:
                raise
            arts = empty_probe_artifacts(
                enforcement_mode=enforcement,
                reason=f"build_failed:{exc}",
            )

        # Always write a complete set so later stages have stable contracts.
        try:
            ctx.write_json("analysis/run_golden_facts.json", arts["golden_facts"])
            ctx.write_json("transcript/protected_zones.json", arts["protected_zones"])
            ctx.write_json("transcript/speaker_flows.json", arts["speaker_flows"])
            ctx.write_json("vernacular/probe_report.json", arts["probe_report"])
            ctx.write_json(
                "vernacular/audio_tags_by_flow.json",
                {"version": 1, "by_flow": arts.get("audio_tags_by_flow") or {}},
            )
        except Exception as exc:  # noqa: BLE001
            ctx.log(
                f"audio_probe_build write failed: {exc}",
                level="error",
                stage=stage,
                action_id="audio_probes.write.fail",
                detail={"error": str(exc)[:400]},
            )
            if not fail_open:
                raise
            return

        gf = arts.get("golden_facts") if isinstance(arts.get("golden_facts"), dict) else {}
        ctx.log(
            f"Audio probes: flows={gf.get('meta', {}).get('flows')} "
            f"vernacular={gf.get('run', {}).get('has_in_flow_vernacular')} "
            f"stats={gf.get('meta', {}).get('answer_stats')}",
            stage=stage,
            action_id="audio_probes.build",
            detail={
                "event": "audio_probe_build",
                "vernacular": gf.get("run", {}).get("has_in_flow_vernacular"),
                "zones": len((arts.get("protected_zones") or {}).get("zones") or []),
                "answer_stats": (gf.get("meta") or {}).get("answer_stats"),
                "enforcement_mode": enforcement,
                "has_source_wav": bool(source_wav),
            },
        )
        from interview_mux.stage_completion import heal_or_raise

        heal_or_raise(ctx, stage)


def persist_vernacular_skip(ctx: RunContext, skip_reason: str) -> dict[str, Any]:
    """HS-5: honest skip stub so heal can complete without a hollow marker."""
    report = {
        "version": 1,
        "rows": [],
        "must_keep_segment_ids": [],
        "skipped": skip_reason,
    }
    ctx.write_json(
        "vernacular/resplit_report.json",
        report,
        stage_key="vernacular_segment_sanitize",
    )
    ctx.write_json(
        "analysis/vernacular_must_keep.json",
        {
            "version": 1,
            "must_keep_segment_ids": [],
            "enforcement_mode": enforcement_mode_for_ctx(ctx),
            "skipped": skip_reason,
        },
        stage_key="vernacular_segment_sanitize",
    )
    return report


def _heal_vernacular_done(ctx: RunContext) -> None:
    from interview_mux.stage_completion import heal_or_refuse_mark

    heal_or_refuse_mark(ctx, "vernacular_segment_sanitize", force=True)


def run_vernacular_segment_sanitize(ctx: RunContext) -> None:
    """N-way split segments intersecting protected zones; refresh must_keep ids."""
    stage = "vernacular_segment_sanitize"
    cfg = dict((merged_config().get("audio_probes") or {}))
    fail_open = bool(cfg.get("fail_open", True))

    zones = _safe_read_json(ctx, "transcript/protected_zones.json", stage=stage)
    if zones is None:
        ctx.log(
            "vernacular_segment_sanitize: no protected_zones; writing empty report",
            stage=stage,
            action_id="vernacular.sanitize.skip",
            detail={"reason": "missing_or_corrupt_zones"},
        )
        persist_vernacular_skip(ctx, "no_zones")
        _heal_vernacular_done(ctx)
        return

    if not ctx.artifact_exists("segments/manifest.json"):
        ctx.log(
            "vernacular_segment_sanitize: no manifest yet; skip",
            stage=stage,
            action_id="vernacular.sanitize.skip",
            detail={"reason": "no_manifest"},
        )
        persist_vernacular_skip(ctx, "no_manifest")
        _heal_vernacular_done(ctx)
        return

    manifest = _safe_read_json(ctx, "segments/manifest.json", stage=stage)
    if manifest is None:
        ctx.log(
            "vernacular_segment_sanitize: corrupt manifest; abort sanitize",
            level="warning",
            stage=stage,
            action_id="vernacular.sanitize.fail_open",
            detail={"reason": "corrupt_manifest"},
        )
        if not fail_open:
            raise RuntimeError("segments/manifest.json unreadable")
        persist_vernacular_skip(ctx, "corrupt_manifest")
        _heal_vernacular_done(ctx)
        return

    # Merge flow-level audio tags onto overlapping segments (fault-tolerant advisory).
    tags_doc = _safe_read_json(ctx, "vernacular/audio_tags_by_flow.json", stage=stage) or {}
    tags_by_flow = tags_doc.get("by_flow") if isinstance(tags_doc.get("by_flow"), dict) else {}
    flows_doc = _safe_read_json(ctx, "transcript/speaker_flows.json", stage=stage) or {}
    flows = [f for f in (flows_doc.get("flows") or []) if isinstance(f, dict)]

    if not (zones.get("zones") or []):
        persist_vernacular_skip(ctx, "empty_zones")
        ctx.log(
            "vernacular_segment_sanitize: empty zones",
            stage=stage,
            action_id="vernacular.sanitize.skip",
            detail={"reason": "empty_zones"},
        )
        _heal_vernacular_done(ctx)
        return

    min_child = int((cfg.get("sanitize") or {}).get("min_child_ms") or 800)

    with logged_step(f"{stage}/nway_resplit", ctx=ctx, stage=stage):
        try:
            result = sanitize_manifest_with_zones(manifest, zones, min_child_ms=min_child)
        except Exception as exc:  # noqa: BLE001
            ctx.log(
                f"Sanitize failed: {exc}",
                level="error",
                stage=stage,
                action_id="vernacular.sanitize.fail",
                detail={"error": str(exc)[:400]},
            )
            if not fail_open:
                raise
            ctx.write_json(
                "vernacular/resplit_report.json",
                {
                    "version": 1,
                    "rows": [],
                    "must_keep_segment_ids": [],
                    "error": str(exc)[:300],
                },
                stage_key="vernacular_segment_sanitize",
            )
            _heal_vernacular_done(ctx)
            return

        # Propagate flow tags onto children that overlap the flow window.
        segs = result["manifest"].get("segments") or []
        if tags_by_flow and flows:
            for s in segs:
                if not isinstance(s, dict):
                    continue
                try:
                    a, b = int(s.get("start_ms") or 0), int(s.get("end_ms") or 0)
                except (TypeError, ValueError):
                    continue
                for fl in flows:
                    fid = str(fl.get("speaker_flow_id") or "")
                    ft = tags_by_flow.get(fid)
                    if not isinstance(ft, dict):
                        continue
                    try:
                        f0, f1 = int(fl.get("start_ms") or 0), int(fl.get("end_ms") or 0)
                    except (TypeError, ValueError):
                        continue
                    if min(b, f1) - max(a, f0) <= 0:
                        continue
                    tags = dict(s.get("audio_tags") or {})
                    for k in ("passion_level", "speech_act", "keywords", "spans"):
                        if k in ft and k not in tags:
                            tags[k] = ft[k]
                    if ft.get("is_special") and not tags.get("is_special"):
                        tags["near_special_flow"] = True
                    s["audio_tags"] = tags

        try:
            from interview_mux.artifact_lifecycle import fingerprint_artifact

            ctx.write_json(
                "segments/manifest.json",
                fingerprint_artifact(result["manifest"], stage),
                stage_key=stage,
            )
            ctx.write_json(
                "vernacular/resplit_report.json",
                fingerprint_artifact(result["resplit_report"], stage),
                stage_key=stage,
            )
        except Exception as exc:  # noqa: BLE001
            ctx.log(
                f"Sanitize write failed: {exc}",
                level="error",
                stage=stage,
                action_id="vernacular.sanitize.write_fail",
                detail={"error": str(exc)[:300]},
            )
            if not fail_open:
                raise
            return

        mode = enforcement_mode_for_ctx(ctx)
        # Side-car is the vernacular-owned record. Do not mutate
        # analysis/run_golden_facts.json (audio_probe_build owner) — that DENY
        # aborted sanitize after a successful manifest resplit (exec_11871).
        ctx.write_json(
            "analysis/vernacular_must_keep.json",
            {
                "version": 1,
                "must_keep_segment_ids": result["must_keep_segment_ids"],
                "enforcement_mode": mode,
            },
            stage_key=stage,
        )

        updated_zones = []
        for z in zones.get("zones") or []:
            if not isinstance(z, dict):
                continue
            zz = dict(z)
            z0, z1 = int(zz.get("start_ms") or 0), int(zz.get("end_ms") or 0)
            ids = []
            for s in segs:
                if not isinstance(s, dict):
                    continue
                if (s.get("audio_tags") or {}).get("is_special"):
                    try:
                        a, b = int(s.get("start_ms") or 0), int(s.get("end_ms") or 0)
                    except (TypeError, ValueError):
                        continue
                    if min(b, z1) - max(a, z0) > 0:
                        ids.append(str(s.get("segment_id")))
            zz["segment_ids"] = ids
            updated_zones.append(zz)
        zones_out = dict(zones)
        zones_out["zones"] = updated_zones
        ctx.write_json("transcript/protected_zones.json", zones_out, stage_key=stage)

        ctx.log(
            f"Vernacular sanitize: splits={len(result['resplit_report'].get('rows') or [])} "
            f"must_keep={len(result['must_keep_segment_ids'])} mode={mode}",
            stage=stage,
            action_id="vernacular.sanitize",
            detail={
                "event": "vernacular_segment_sanitize",
                "must_keep": result["must_keep_segment_ids"][:20],
                "enforcement_mode": mode,
                "patterns": [
                    r.get("pattern") for r in (result["resplit_report"].get("rows") or [])[:12]
                ],
            },
        )
        _heal_vernacular_done(ctx)
        if mode == "shadow" and result["must_keep_segment_ids"]:
            ctx.log(
                "Shadow mode: vernacular must_keep recorded but not hard-enforced",
                level="info",
                stage=stage,
                action_id="vernacular.shadow.recorded",
                detail={"must_keep": result["must_keep_segment_ids"][:20]},
            )
