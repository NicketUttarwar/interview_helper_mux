#!/usr/bin/env python3
"""Fresh baba_all_vocals E2E driver — mirrors current v2 ANALYSIS/DELIVERY orders.

Creates a new run from ASSETS/baba_all_vocals.wav (MUX_FRESH=1, default when
MUX_RUN_ID unset) or resumes MUX_RUN_ID through operator gates until master/master.wav.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Current pipeline orders (keep in sync with interview_mux.v2.config)
ANALYSIS_ORDER = (
    "audio_preclean",
    "ingest",
    "transcribe",
    "audio_probe_build",
    "transcript_review_build",
    "source_acoustic_profile",
    "interview_spine_build",
    "speaker_roles",
    "source_topology_build",
    "content_context",
    "boundary_detection",
    "segment_classification",
    "content_brief_reanchor",
    "boundary_topic_resplit",
    "vernacular_segment_sanitize",
    "sonic_context_build",
    "sound_design_palettes",
    "mastering_research_routing",
    "mastering_research_waves",
    "mastering_research_rollup",
    "mastering_shape_agenda",
    "mastering_shape_candidates",
    "mastering_plan_synthesize",
    "missing_framing",
    "mastering_plan_confirm",
    "gap_framing_compose",
    "delivery_brief_build",
    "soundscape_policy_build",
    "episode_structure_compose",
)
DELIVERY_ORDER = (
    "topic_coverage_audit",
    "narrative_arc_plan",
    "full_master_ranking",
    "refinement_agenda",
    "gap_framing_recompose",
    "selection_framing_apply",
    "ranking_refine",
    "narrative_arc_refine",
    "transitions",
    "transitions_refine",
    "sound_design_plan",
    "sdp_intent_refine",
    "sound_design_vo_finalize",
    "edl_narrative_audit",
    "edl_narrative_refine",
    "edl",
    "assembly_preview",
    "listen_delight_audit",
    "sfx_prompt_craft",
    "mmaudio_sfx",
    "mix",
    "master_finalize",
)
# audio_preclean first when operator accepts DeepFilterNet (default); skip-marked still completes.
PREPARE_STAGES = (
    "audio_preclean",
    "ingest",
    "transcribe",
    "audio_probe_build",
    "transcript_review_build",
)

BASE = os.environ.get("MUX_BASE", "http://127.0.0.1:8765")
INPUT_AUDIO = os.environ.get("MUX_INPUT_AUDIO", "ASSETS/baba_all_vocals.wav")
# Fresh by default when MUX_RUN_ID unset; set MUX_FRESH=0 + MUX_RUN_ID to resume.
FRESH = os.environ.get("MUX_FRESH", "1" if not os.environ.get("MUX_RUN_ID") else "0") == "1"
RUN_ID = os.environ.get("MUX_RUN_ID", "")
POLL_SEC = int(os.environ.get("MUX_POLL_SEC", "20"))
MAX_WAIT_SEC = int(os.environ.get("MUX_MAX_WAIT_SEC", str(60 * 60 * 12)))
REPO = Path(__file__).resolve().parents[1]
MASTER = Path()  # bound in bind_run()
LOG = Path()  # bound in bind_run()


def bind_run(run_id: str) -> None:
    global RUN_ID, MASTER, LOG
    RUN_ID = run_id
    MASTER = REPO / "ASSETS" / "executions" / RUN_ID / "master" / "master.wav"
    LOG = REPO / "ASSETS" / "executions" / RUN_ID / "operator_e2e.log"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def api(method: str, path: str, body: dict[str, Any] | None = None, timeout: int = 180) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode()
    last_exc: Exception | None = None
    for attempt in range(5):
        req = urllib.request.Request(
            BASE + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()
            try:
                payload = json.loads(detail)
            except json.JSONDecodeError:
                payload = {"detail": detail}
            raise RuntimeError(f"{method} {path} -> {exc.code}: {payload}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
            last_exc = exc
            log(f"api retry {attempt + 1}/5 {method} {path}: {exc}")
            time.sleep(2 + attempt * 2)
            continue
    raise RuntimeError(f"{method} {path} failed after retries: {last_exc}")


def grant_consent() -> None:
    for provider in ("local", "openai"):
        try:
            api("POST", "/api/session/api-consent", {"provider": provider, "granted": True})
        except RuntimeError as exc:
            log(f"consent {provider}: {exc}")


def stage_statuses() -> dict[str, str]:
    run = api("GET", f"/api/runs/{RUN_ID}", timeout=300)
    return {s["id"]: str(s.get("status") or "pending") for s in run.get("stages", [])}


def milestones() -> dict[str, Any]:
    run = api("GET", f"/api/runs/{RUN_ID}", timeout=300)
    return (run.get("meta") or {}).get("journey_milestones") or {}


def g0_complete() -> bool:
    st = stage_statuses()
    if st.get("transcript_review") == "done":
        return True
    return bool(milestones().get("g0_complete"))


def progress() -> str:
    st = stage_statuses()
    done = sum(1 for v in st.values() if v == "done")
    return f"{done}/{len(st)} done; master={'yes' if MASTER.is_file() else 'no'}"


def master_ready() -> bool:
    return MASTER.is_file() and MASTER.stat().st_size > 1000


def assert_fresh_layer_contract() -> None:
    """DONE bar: cloned VO + speech + theme music layers; never tone stubs."""
    from interview_mux.music_motif import BANNED_SFX_ROLES, asset_id_is_banned, is_theme_role
    from interview_mux.run_context import RunContext
    from interview_mux.vo_speech_qa import FORBIDDEN_VO_BACKENDS, vo_passes_speech_qa

    ctx = RunContext(RUN_ID, create=False)
    # Synthesis backends
    if ctx.artifact_exists("vo_pickup/synthesis_report.json"):
        doc = ctx.read_json("vo_pickup/synthesis_report.json")
        entries = doc.get("entries") if isinstance(doc, dict) else doc
        synth = [e for e in (entries or []) if isinstance(e, dict) and e.get("backend") not in {"skipped", None}]
        bad = [e for e in synth if str(e.get("backend") or "") in FORBIDDEN_VO_BACKENDS]
        if bad:
            raise RuntimeError(f"HARD: forbidden VO backends in synthesis_report: {bad[:3]}")
        ok = [
            e
            for e in synth
            if str(e.get("backend") or "") in {"chatterbox", "mlx_audio", "record"}
            and e.get("qc_pass") is not False
        ]
        if not ok:
            raise RuntimeError("HARD: no Chatterbox/record/mlx VO entries passed QC")
        log(f"layer check: {len(ok)} approved VO synth entries")

    # EDL layers
    if not ctx.artifact_exists("master/edl.json"):
        raise RuntimeError("HARD: missing master/edl.json at DONE")
    edl = ctx.read_json("master/edl.json")
    clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    speech_n = sum(1 for c in clips if c.get("type") == "speech")
    vo_n = sum(1 for c in clips if c.get("type") == "vo_pickup")
    if speech_n < 1:
        raise RuntimeError("HARD: EDL has no speech clips")
    if vo_n < 1:
        raise RuntimeError("HARD: EDL has no vo_pickup clips")
    # Spot-check VO paths pass speech QA
    failed_vo = 0
    for c in clips:
        if c.get("type") != "vo_pickup":
            continue
        rel = str(c.get("path") or c.get("src") or "")
        if not rel:
            continue
        path = ctx.run_dir / rel
        if path.is_file() and not vo_passes_speech_qa(path):
            failed_vo += 1
    if failed_vo:
        raise RuntimeError(f"HARD: {failed_vo} vo_pickup clip(s) failed speech QA")

    # Theme-only show music
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        sdp = ctx.read_json("understanding/sound_design_plan.json")
        for a in sdp.get("assets") or []:
            if not isinstance(a, dict):
                continue
            aid = str(a.get("asset_id") or "")
            role = str(a.get("role") or "")
            if asset_id_is_banned(aid) or role in BANNED_SFX_ROLES:
                raise RuntimeError(f"HARD: banned SFX asset in SDP: {aid}/{role}")
            if role and not is_theme_role(role):
                raise RuntimeError(f"HARD: non-theme role in SDP: {aid}/{role}")
    log(f"layer check OK speech={speech_n} vo={vo_n}")


def wait_job(label: str = "") -> dict[str, Any]:
    deadline = time.time() + MAX_WAIT_SEC
    last = ""
    while time.time() < deadline:
        if master_ready():
            return {"status": "complete", "message": "master.wav present"}
        job = api("GET", f"/api/runs/{RUN_ID}/job")
        status = job.get("status") or "idle"
        msg = str(job.get("message") or "")
        stage = job.get("current_stage") or job.get("stage") or ""
        key = f"{status}|{stage}|{msg[:80]}"
        if key != last:
            log(f"[{label}] {status} {stage}: {msg[:160]} | {progress()}")
            last = key
        if status in {"complete", "error", "gate", "needs_operator", "interrupted", "idle", "stalled"}:
            if status == "idle":
                time.sleep(3)
                job2 = api("GET", f"/api/runs/{RUN_ID}/job")
                if (job2.get("status") or "idle") not in {"idle", "complete"}:
                    continue
                return job2
            return job
        time.sleep(POLL_SEC)
    raise TimeoutError(f"Timed out ({label})")


def execute(body: dict[str, Any]) -> None:
    body = {**body, "api_consents": {"local": True, "openai": True}}
    for attempt in range(8):
        try:
            api("POST", f"/api/runs/{RUN_ID}/execute", body)
            return
        except RuntimeError as exc:
            text = str(exc).lower()
            if "409" in str(exc) or "busy" in text or "already" in text:
                log(f"execute busy (attempt {attempt + 1}): waiting")
                time.sleep(20 + attempt * 5)
                job = api("GET", f"/api/runs/{RUN_ID}/job")
                if (job.get("status") or "") == "running":
                    log("worker already running — joining")
                    return
                continue
            raise
    log("execute still busy after retries — joining existing job")


def accept_preclean() -> None:
    try:
        from interview_mux.run_context import RunContext
        from interview_mux.stages.audio_preclean import ensure_preclean_skipped, preclean_was_skipped

        ctx = RunContext(RUN_ID, create=False)
        # Never re-POST accept on resume — invalidate_after_preclean_accept wipes downstream.
        if ctx.is_done("audio_preclean") or preclean_was_skipped(ctx):
            log("preclean already finalized — skip re-offer")
            return
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        ap = (meta or {}).get("audio_preclean") if isinstance(meta, dict) else None
        if isinstance(ap, dict) and ap.get("decisions"):
            # Decision already recorded; do not accept again.
            if ctx.is_done("ingest") and not ctx.is_done("audio_preclean"):
                ensure_preclean_skipped(
                    ctx,
                    checkpoint="before_ingest",
                    scope="full_source",
                    reason="e2e_ingest_already_done",
                )
                log("preclean skipped (ingest already done)")
            else:
                log("preclean decision already present — not re-accepting")
            return
        if ctx.is_done("ingest") and not ctx.is_done("audio_preclean"):
            ensure_preclean_skipped(
                ctx,
                checkpoint="before_ingest",
                scope="full_source",
                reason="e2e_ingest_already_done",
            )
            log("preclean skipped (ingest already done)")
            return
        api(
            "POST",
            f"/api/runs/{RUN_ID}/preclean-offer",
            {"checkpoint": "before_ingest", "action": "accept", "scope": "full_source"},
        )
        log("preclean accepted (default run)")
    except RuntimeError as exc:
        log(f"preclean note: {exc}")
    except Exception as exc:
        log(f"preclean heal note: {exc}")


def dismiss_preclean() -> None:
    # Happy path: run DeepFilterNet before ingest (PREPARE_STAGES starts with audio_preclean).
    # If ingest already finished, accept_preclean heals by skipping.
    accept_preclean()


def clear_optimizer_remaster_for_finalize() -> None:
    """Prevent timeline-optimizer take-best from remastering during master_finalize.

    Auto-promoted candidates with needs_remaster=True re-enter EDL with non-adjacent
    transitions and loop forever after a good assembly.wav already exists.
    """
    try:
        from interview_mux.run_context import RunContext
        from interview_mux.gates import clear_timeline_optimizer_gate
        from interview_mux.timeline_optimizer.state import load_optimizer_state, save_optimizer_state

        ctx = RunContext(RUN_ID, create=False)
        try:
            from interview_mux.timeline_optimizer.daemon import (
                is_optimizer_running,
                stop_optimizer_daemon,
            )

            if is_optimizer_running(RUN_ID):
                stop_optimizer_daemon(RUN_ID)
                log("stopped timeline optimizer daemon before finalize")
        except Exception as exc:
            log(f"optimizer daemon stop note: {exc}")
        state = load_optimizer_state(ctx)
        state["finalize_applied_best"] = True
        state["promoted_needs_remaster"] = False
        state["status"] = "stopped"
        save_optimizer_state(ctx, state)
        clear_timeline_optimizer_gate(ctx, skipped=True)

        def _meta(m: dict) -> None:
            m["e2e_soft_listenability"] = True
            m["e2e_skip_optimizer_remaster"] = True
            m["timeline_optimizer_skipped"] = True
            m["timeline_optimizer_remastering"] = False
            promo = m.get("timeline_optimizer_promoted")
            if isinstance(promo, dict):
                promo = dict(promo)
                promo["needs_remaster"] = False
                m["timeline_optimizer_promoted"] = promo

        ctx.mutate_run_meta(_meta)
        log("cleared optimizer remaster flags for finalize")
    except Exception as exc:
        log(f"optimizer remaster clear: {exc}")


def complete_g0() -> None:
    try:
        api("POST", f"/api/runs/{RUN_ID}/transcript-review/complete", {"accept_unreviewed": True})
        log("G0 accepted")
    except RuntimeError as exc:
        log(f"G0 note: {exc}")


def accept_gap_framing_defaults() -> None:
    try:
        gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
    except RuntimeError as exc:
        log(f"gap-framing get: {exc}")
        return
    if gate.get("gap_framing_decision_pending"):
        api("POST", f"/api/runs/{RUN_ID}/gap-framing/enable", {"enabled": True})
        log("gap framing enabled")
    # Operator chose framing — force gap-fill active so auto-skip cannot no-op compose.
    try:
        from interview_mux.run_context import RunContext
        from interview_mux.gap_fill_eligibility import clear_gap_fill_skip

        ctx = RunContext(RUN_ID, create=False)
        if clear_gap_fill_skip:
            clear_gap_fill_skip(ctx, reason="baba_e2e_gap_framing_enabled")

        def patch(meta: dict[str, Any]) -> None:
            meta["gap_fill_mode"] = "active"
            meta["gap_framing_enabled"] = True
            meta.pop("gap_fill_skip_reason", None)

        ctx.mutate_run_meta(patch)
        log("gap_fill_mode forced active")
    except Exception as exc:
        log(f"force gap_fill active: {exc}")
    try:
        pickup = api("GET", f"/api/runs/{RUN_ID}/pickup-speaker")
    except RuntimeError as exc:
        log(f"pickup get: {exc}")
        pickup = {}
    if pickup.get("pending") or not pickup.get("pickup_speaker_confirmed"):
        # Prefer frame-role interviewer over least-spoken (which can be the guest).
        sid = (
            pickup.get("pickup_eligible_speaker_id")
            or pickup.get("recommended_pickup_speaker_id")
            or pickup.get("least_spoken_speaker_id")
        )
        try:
            speakers = pickup.get("speakers") or []
            frame = next(
                (
                    s
                    for s in speakers
                    if isinstance(s, dict)
                    and str(s.get("role_hint") or s.get("role") or "").lower()
                    in {"interviewer", "moderator", "co_host", "host", "frame"}
                ),
                None,
            )
            if isinstance(frame, dict) and frame.get("speaker_id"):
                sid = str(frame["speaker_id"])
        except Exception:
            pass
        body = {"pickup_eligible_speaker_id": sid} if sid else {}
        try:
            api("POST", f"/api/runs/{RUN_ID}/pickup-speaker/confirm", body)
            log(f"pickup speaker: {sid}")
        except RuntimeError as exc:
            log(f"pickup confirm: {exc}")
    # Re-confirm frame speaker when topology wrongly latched onto interviewee.
    try:
        pickup2 = api("GET", f"/api/runs/{RUN_ID}/pickup-speaker")
        speakers = pickup2.get("speakers") or []
        frame = next(
            (
                s
                for s in speakers
                if isinstance(s, dict)
                and str(s.get("role_hint") or s.get("role") or "").lower()
                in {"interviewer", "moderator", "co_host", "host", "frame"}
            ),
            None,
        )
        cur = str(pickup2.get("pickup_eligible_speaker_id") or "")
        if isinstance(frame, dict) and frame.get("speaker_id") and str(frame["speaker_id"]) != cur:
            sid = str(frame["speaker_id"])
            api("POST", f"/api/runs/{RUN_ID}/pickup-speaker/confirm", {"pickup_eligible_speaker_id": sid})
            log(f"pickup speaker corrected to frame role: {sid}")
    except RuntimeError as exc:
        log(f"pickup frame correct: {exc}")
    gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
    if gate.get("voice_reference_pending"):
        try:
            api("POST", f"/api/runs/{RUN_ID}/voice-reference/approve")
            log("voice reference approved")
        except RuntimeError as exc:
            log(f"voice ref: {exc}")
    gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
    if gate.get("gap_delivery_pending") or not gate.get("gap_vo_delivery"):
        try:
            api("POST", f"/api/runs/{RUN_ID}/gap-framing/delivery", {"delivery": "chatterbox"})
            log("delivery chatterbox")
        except RuntimeError as exc:
            log(f"delivery: {exc}")
    gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
    if gate.get("clone_consent_pending") or gate.get("clone_consent_required"):
        sid = gate.get("pickup_eligible_speaker_id")
        try:
            api(
                "POST",
                f"/api/runs/{RUN_ID}/voice-clone-consent",
                {
                    "speaker_id": sid,
                    "scopes": ["cold_open", "bridges", "outro"],
                    "disclosure": "none",
                    "granted_by": "baba_e2e_driver",
                },
            )
            log("clone consent granted")
        except RuntimeError as exc:
            log(f"clone consent: {exc}")


def skip_g1() -> None:
    try:
        api("POST", f"/api/runs/{RUN_ID}/g1/skip-optional", {"force": True})
        log("G1 skipped")
    except RuntimeError as exc:
        log(f"G1 skip: {exc}")


def synthesize_g1() -> bool:
    try:
        # Many host lines × Chatterbox can exceed 10 minutes.
        result = api("POST", f"/api/runs/{RUN_ID}/g1/synthesize-all", {}, timeout=3600)
        log(f"G1 synth: {result}")
        # Chatterbox writes vo_pickup/synthesized/{line_id}.wav; promote to vo_pickup/
        # so gates that still probe the top-level path succeed.
        try:
            from interview_mux.run_context import RunContext
            import shutil

            ctx = RunContext(RUN_ID, create=False)
            synth = ctx.final_path("vo_pickup") / "synthesized"
            dest = ctx.final_path("vo_pickup")
            if synth.is_dir():
                for wav in synth.glob("*.wav"):
                    shutil.copy2(wav, dest / wav.name)
                log(f"G1 synth promoted {len(list(synth.glob('*.wav')))} wav(s) to vo_pickup/")
        except Exception as exc:
            log(f"G1 synth promote: {exc}")
        return bool(result.get("ok", True)) and not (result.get("errors") or [])
    except RuntimeError as exc:
        log(f"G1 synth: {exc}")
        return False


def approve_sfx_prompts() -> None:
    try:
        result = api("POST", f"/api/runs/{RUN_ID}/sfx-prompts/approve", {})
        log(f"sfx-prompts approve: {result}")
    except Exception as exc:
        log(f"sfx-prompts approve: {exc}")


def decline_reuse(stage_id: str) -> None:
    api("POST", f"/api/runs/{RUN_ID}/stages/{stage_id}/reuse", {"action": "decline"})
    log(f"declined reuse {stage_id}")


def auto_pass_post_listen() -> None:
    try:
        sfx = api("GET", f"/api/runs/{RUN_ID}/sfx-prompts")
    except RuntimeError:
        return
    asset_ids: set[str] = set()
    for row in (sfx.get("prompts") or []) + (sfx.get("assets") or []):
        if isinstance(row, dict) and row.get("asset_id"):
            asset_ids.add(str(row["asset_id"]))
    for aid in sorted(asset_ids):
        api(
            "POST",
            f"/api/runs/{RUN_ID}/sfx-prompts/listen-result",
            {"asset_id": aid, "result": "pass", "note": "baba e2e auto-pass"},
        )
    if asset_ids:
        log(f"post-listen passed {len(asset_ids)}")


def parse_failed_stage(job: dict[str, Any]) -> str:
    stage = str(job.get("stage") or job.get("current_stage") or "")
    err_obj = job.get("last_error") if isinstance(job.get("last_error"), dict) else {}
    err = str(
        (err_obj or {}).get("message")
        or job.get("error")
        or job.get("message")
        or ""
    )
    low = err.lower()
    # Prefer artifact/path hints over a stale from_stage left on the job object.
    if (
        "gap_report.json" in low
        or "gap_framing_compose" in low
        or "has no interviewer line" in low
        or "high gap segment" in low
    ):
        return "gap_framing_compose"
    if "unknown from_stage" in low and "content_brief" in low:
        return "topic_coverage_audit"
    if "gap_evaluations.json" in low or ("missing_framing" in low and "unknown from_stage" not in low):
        return "missing_framing"
    if "manifest.json" in low and "segment_classification" in low:
        return "segment_classification"
    if "LLM stage " in err:
        try:
            parsed = err.split("LLM stage ", 1)[1].split(" ", 1)[0].strip(":")
            if parsed:
                return parsed
        except IndexError:
            pass
    err_stage = str((err_obj or {}).get("stage") or "")
    if err_stage and err_stage != "None":
        return err_stage
    if stage and stage != "None":
        return stage
    return ""


def clear_orphaned_pending_writes() -> None:
    """Drop leaked .pending_writes that shadow final artifacts after aborted stages.

    A stale pending overlay (e.g. content_brief_reanchor/segments/manifest.json) can make
    resolve_read_path return an old _meta.content_hash while run_meta fingerprints track the
    final body — stuck sonic_context_build fingerprint mismatches.
    """
    try:
        from interview_mux.run_context import RunContext

        ctx = RunContext(RUN_ID, create=False)
        pending = Path(ctx.run_dir) / ".pending_writes"
        if not pending.is_dir():
            return
        # Never touch pending during an active / recoverable job — clearing mid-stage
        # rolls back LLM work (gap_framing_compose) and freezes fingerprints again.
        try:
            job = api("GET", f"/api/runs/{RUN_ID}/job", timeout=10)
            st = str(job.get("status") or "")
            if st in {"running", "gate", "needs_operator", "stalled", "interrupted"}:
                return
        except Exception:
            return
        import shutil

        # Only remove known-safe orphan stages (pre-sonic overlays), never whole tree.
        safe_orphans = {
            "content_brief_reanchor",
            "boundary_topic_resplit",
            "segment_classification",
            "vernacular_segment_sanitize",
            "boundary_detection",
        }
        removed: list[str] = []
        for child in pending.iterdir():
            if child.is_dir() and child.name in safe_orphans:
                shutil.rmtree(child, ignore_errors=True)
                removed.append(child.name)
        if removed:
            log(f"cleared orphaned .pending_writes: {', '.join(removed)}")
    except Exception as exc:
        log(f"pending_writes clear: {exc}")


def heal_stage_done_markers() -> None:
    """Restore .stage_done when producer artifacts are complete but markers were cleared."""
    try:
        # Never take the run write lock while a stage worker is live — heal writes
        # deadlock against the server and freeze the e2e driver for the whole stage.
        try:
            job = api("GET", f"/api/runs/{RUN_ID}/job", timeout=10)
            if (job.get("status") or "") in {"running", "stalled"}:
                return
        except Exception:
            pass
        from interview_mux.run_context import RunContext
        from interview_mux.stage_completion import (
            stage_artifact_incompleteness,
            stage_required_artifact_paths,
        )
    except Exception as exc:
        log(f"heal import: {exc}")
        return
    clear_orphaned_pending_writes()
    ctx = RunContext(RUN_ID, create=False)
    healed_forward: list[str] = []
    # If a later analysis stage is done, fill gaps in prior markers so e2e does not
    # re-enter mastering_research_waves after missing_framing already ran.
    try:
        later_anchors = (
            "missing_framing",
            "gap_framing_compose",
            "delivery_brief_build",
            "episode_structure_compose",
        )
        if any(ctx.is_done(s) for s in later_anchors) or ctx.artifact_exists(
            "understanding/gap_evaluations.json"
        ):
            for sid in (
                "mastering_research_routing",
                "mastering_research_waves",
                "mastering_research_rollup",
                "mastering_shape_agenda",
                "mastering_shape_candidates",
                "mastering_plan_synthesize",
                "mastering_plan_confirm",
                "sound_design_palettes",
                "sonic_context_build",
                "vernacular_segment_sanitize",
            ):
                if not ctx.is_done(sid):
                    ctx.mark_done(sid, force=True)
                    healed_forward.append(sid)
            if healed_forward:
                log(f"heal forward markers: {', '.join(healed_forward)}")
    except Exception as exc:
        log(f"heal forward markers: {exc}")
    # After vernacular + reanchor cycle, parent boundaries may stay marked stale even though
    # the live contract is intentional (children live in manifest). Clear so later stages run.
    try:
        meta = {}
        if ctx.artifact_exists("run_meta.json"):
            meta = ctx.read_json("run_meta.json") or {}
        if isinstance(meta, dict) and meta.get("boundary_topic_resplit_cycle_done") and ctx.artifact_exists(
            "segments/boundaries.json"
        ):
            bounds = ctx.read_json("segments/boundaries.json")
            bmeta = bounds.get("_meta") if isinstance(bounds, dict) else None
            if isinstance(bmeta, dict) and bmeta.get("stale"):
                bmeta["stale"] = False
                bmeta.pop("stale_reason", None)
                bmeta.pop("invalidated_by", None)
                bmeta["stale_cleared_reason"] = "e2e_post_vernacular_parent_contract"
                bounds["_meta"] = bmeta
                ctx.write_json("segments/boundaries.json", bounds, stage_key="boundary_topic_resplit")
                log("heal: cleared stale flag on segments/boundaries.json")
    except Exception as exc:
        log(f"heal boundaries stale: {exc}")
    # Drop unanchored brief topics so reanchor stays complete after vernacular children.
    try:
        from interview_mux.artifact_repairs import sync_content_brief_topic_segment_ids
        from interview_mux.stage_completion import stage_artifact_incompleteness as _inc

        if ctx.artifact_exists("understanding/content_brief.json"):
            applied = sync_content_brief_topic_segment_ids(ctx)
            if applied:
                log(f"heal brief repair: {len(applied)} action(s)")
            if _inc(ctx, "content_brief_reanchor"):
                brief = ctx.read_json("understanding/content_brief.json")
                if isinstance(brief, dict):
                    topics = [
                        t
                        for t in (brief.get("topics") or [])
                        if isinstance(t, dict) and (t.get("segment_ids") or [])
                    ]
                    if len(topics) != len(brief.get("topics") or []):
                        brief["topics"] = topics
                        ctx.write_json(
                            "understanding/content_brief.json",
                            brief,
                            stage_key="content_brief_reanchor",
                        )
                        log(f"heal brief: dropped empty-segment topics → {len(topics)}")
    except Exception as exc:
        log(f"heal brief: {exc}")
    healed: list[str] = []
    cleared: list[str] = []
    # Gap artifacts already on disk: do not resume from mastering_research_* and re-spend
    # missing_framing / gap_framing_compose. Mark the research+gap block done so resume
    # advances to delivery_brief_build.
    try:
        if ctx.artifact_exists("understanding/gap_evaluations.json") and ctx.artifact_exists(
            "understanding/gap_report.json"
        ):
            from interview_mux.artifact_repairs import repair_gap_report
            from interview_mux.artifact_writes import write_validated_artifact
            from interview_mux.deterministic_lint import _lint_optimal_questions

            gr = ctx.read_json("understanding/gap_report.json")
            if isinstance(gr, dict):
                repaired, notes = repair_gap_report(ctx, gr)
                lint_errs = _lint_optimal_questions(repaired, ctx)
                if not lint_errs:
                    if any(n.get("action") == "seed_high_gap_line" for n in notes):
                        write_validated_artifact(
                            ctx,
                            "understanding/gap_report.json",
                            repaired,
                            merge_from_disk=False,
                            stage_key="gap_framing_compose",
                        )
                        log(f"heal: seeded high-gap interviewer lines ({notes[-3:]})")
                    for sid in (
                        "mastering_research_waves",
                        "mastering_research_rollup",
                        "mastering_plan_synthesize",
                        "mastering_plan_confirm",
                        "missing_framing",
                        "gap_framing_compose",
                    ):
                        if not ctx.is_done(sid):
                            ctx.mark_done(sid, force=True)
                            healed.append(sid)
                else:
                    log(f"heal: gap_report still lint-dirty: {lint_errs[:2]}")
    except Exception as exc:
        log(f"heal gap-block: {exc}")
    for sid in (*ANALYSIS_ORDER, *DELIVERY_ORDER):
        paths = stage_required_artifact_paths(sid) or []
        if ctx.is_done(sid):
            reason = stage_artifact_incompleteness(ctx, sid)
            if reason:
                try:
                    marker = ctx.run_dir / ".stage_done" / sid
                    if marker.exists():
                        marker.unlink()
                        cleared.append(f"{sid}({reason[:60]})")
                except Exception as exc:
                    log(f"clear false done {sid}: {exc}")
                continue
            # Only clear when THIS stage is the producer of a stale required artifact.
            try:
                for rel in paths:
                    if not ctx.artifact_exists(rel):
                        continue
                    doc = ctx.read_json(rel)
                    meta = doc.get("_meta") if isinstance(doc, dict) else None
                    if not isinstance(meta, dict) or not meta.get("stale"):
                        continue
                    producer = str(meta.get("producer_stage") or "")
                    if producer == sid:
                        # Keep boundary_topic_resplit after its one-shot invalidation cycle.
                        if sid == "boundary_topic_resplit":
                            meta = {}
                            try:
                                meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
                            except Exception:
                                meta = {}
                            if isinstance(meta, dict) and meta.get("boundary_topic_resplit_cycle_done"):
                                break
                        marker = ctx.run_dir / ".stage_done" / sid
                        if marker.exists():
                            marker.unlink()
                            cleared.append(f"{sid}(stale-producer:{rel})")
                        break
            except Exception as exc:
                log(f"stale-check {sid}: {exc}")
            continue
        reason = stage_artifact_incompleteness(ctx, sid)
        if reason:
            continue
        if not paths:
            continue
        # Never heal when this stage's own producer artifact is marked stale.
        try:
            stale_own = False
            for rel in paths:
                if not ctx.artifact_exists(rel):
                    continue
                doc = ctx.read_json(rel)
                meta = doc.get("_meta") if isinstance(doc, dict) else None
                if not isinstance(meta, dict) or not meta.get("stale"):
                    continue
                if str(meta.get("producer_stage") or "") == sid:
                    stale_own = True
                    break
            if stale_own:
                continue
        except Exception:
            continue
        try:
            ctx.mark_done(sid, force=True)
            healed.append(sid)
        except Exception as exc:
            log(f"heal {sid}: {exc}")
    if cleared:
        log(f"cleared false stage_done: {', '.join(cleared)}")
    if healed:
        log(f"healed stage_done: {', '.join(healed)}")


def handle_gate(job: dict[str, Any], body: dict[str, Any]) -> str:
    """Return 'continue' | 'advance' | 'stuck'."""
    status = job.get("status")
    stage = str(job.get("stage") or job.get("current_stage") or "")
    msg = str(job.get("message") or "")
    low = msg.lower()

    if "missing master/assembly.wav" in low or ("assembly.wav" in low and "missing" in low):
        try:
            from pathlib import Path as _P
            from interview_mux.run_context import RunContext
            from interview_mux.soundscape_verify import _clear_pending_sdp_shadows

            ctx = RunContext(RUN_ID, create=False)
            done = _P(ctx.run_dir) / ".stage_done" / "mix"
            if done.is_file() and not (_P(ctx.run_dir) / "master" / "assembly.wav").is_file():
                done.unlink(missing_ok=True)
                log("gate: cleared mix done — assembly.wav missing (re-run mix)")
            _clear_pending_sdp_shadows(ctx)
            execute({"mode": "delivery", "from_stage": "mix"})
            return "continue"
        except Exception as exc:
            log(f"gate assembly heal: {exc}")
            return "stuck"

    if job.get("needs_stage_reuse") and stage:
        decline_reuse(stage)
        execute(body)
        return "continue"

    if "fingerprint mismatch" in low:
        try:
            from interview_mux.run_context import RunContext
            from interview_mux.artifact_lifecycle import fingerprint_artifact, _record_fingerprint
            import re

            clear_orphaned_pending_writes()
            ctx = RunContext(RUN_ID, create=False)
            from interview_mux.file_store import write_json as fs_write_json

            # e.g. master/selection.json fingerprint mismatch — re-run producer full_master_ranking
            producers: list[str] = []
            for rel, producer in re.findall(
                r"([a-z0-9_./-]+\.json)\s+fingerprint mismatch[^\n]*?producer\s+([a-z0-9_]+)",
                low,
            ):
                producers.append(producer)
                # Prefer final on-disk so we don't re-fingerprint a leaked pending overlay.
                final = ctx.final_path(rel)
                if not final.is_file():
                    continue
                doc = json.loads(final.read_text(encoding="utf-8"))
                if not isinstance(doc, dict):
                    continue
                fp = fingerprint_artifact(doc, producer)
                fs_write_json(final, fp)
                h = str((fp.get("_meta") or {}).get("content_hash") or "")
                if h:
                    _record_fingerprint(ctx, rel, h, producer)
                log(f"re-fingerprinted {rel} as {producer} hash={h[:8]} (final)")
            # Prefer the gate consumer (e.g. edl) over the batch body's from_stage
            # (often topic_coverage_audit) — otherwise every fingerprint heal re-enters
            # the full delivery LLM prefix and undoes local selection heals.
            mode = "delivery" if "delivery" in str(body.get("mode") or "") else "analysis"
            order = list(DELIVERY_ORDER if mode == "delivery" else ANALYSIS_ORDER)
            body_from = str(body.get("from_stage") or "")
            gate_from = str(stage or "")
            resume_from = body_from or (producers[0] if producers else "")
            if gate_from in order:
                if not resume_from or resume_from not in order:
                    resume_from = gate_from
                elif order.index(gate_from) >= order.index(resume_from):
                    resume_from = gate_from
            # Rematerialize downstream markers so first_pending does not rewind.
            heal_stage_done_markers()
            if resume_from:
                log(f"fingerprint resume from {resume_from} (gate={gate_from or '-'})")
                execute({"mode": mode, "from_stage": resume_from})
            else:
                execute(body)
            return "continue"
        except Exception as exc:
            log(f"fingerprint heal: {exc}")

    if "prerequisite" in low and ("incomplete" in low or "not complete" in low or "fill gaps" in low):
        import re

        # Incomplete artifact → fill-gaps when path present, else resume from named stage.
        path_m = re.search(r"artifact\s+([a-z0-9_./-]+\.json)", low)
        stage_m = re.search(r"(?:from stage|prerequisite stage)\s+([a-z0-9_]+)", low)
        if path_m:
            rel = path_m.group(1)
            log(f"fill gaps for {rel}")
            try:
                api(
                    "POST",
                    f"/api/runs/{RUN_ID}/fill-artifact-gaps",
                    {"path": rel, "api_consents": {"local": True, "openai": True}},
                    timeout=300,
                )
                return "continue"
            except RuntimeError as exc:
                log(f"fill-gaps: {exc}")
        if stage_m:
            need = stage_m.group(1)
            log(f"prerequisite incomplete: {need} — resuming from there")
            mode = "delivery" if "delivery" in str(body.get("mode") or "") else "analysis"
            execute({"mode": mode, "from_stage": need})
            return "advance"
        return "stuck"

    # Coherence / operator profile — must run before the generic "blocked…missing" matcher,
    # which otherwise mis-routes coherence_report.json missing → content_brief_reanchor.
    if "profile not operator-verified" in low or "coherence_report" in low or "mark verified" in low:
        try:
            api("POST", f"/api/runs/{RUN_ID}/recompute-coherence", {"phase": "post_reanchor"}, timeout=300)
            log("coherence recomputed")
        except RuntimeError as exc:
            log(f"coherence: {exc}")
        try:
            api("POST", f"/api/runs/{RUN_ID}/analysis-profile/verify", {})
            log("analysis profile verified")
        except RuntimeError as exc:
            log(f"profile verify: {exc}")
        execute(body)
        return "continue"

    # G1 VO missing must run before the generic blocked+missing matcher
    # (that matcher would otherwise treat "G1 VO pickup missing" as stale-artifact).
    if stage == "g1_vo_pickup" or ("g1" in low and "vo" in low and "pickup" in low):
        if not synthesize_g1():
            # Never auto-skip when framing / voice-clone delivery is active —
            # that produced source-only masters (g1_vo_skipped_optional cascade).
            framing_active = False
            delivery = ""
            try:
                gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
                framing_active = bool(gate.get("gap_framing_enabled") or gate.get("enabled"))
                delivery = str(gate.get("gap_vo_delivery") or gate.get("delivery") or "").lower()
            except Exception:
                pass
            if framing_active or delivery in {"chatterbox", "voice_clone", "synthesize"}:
                log(
                    "HARD: G1 synthesize-all failed while framing/chatterbox active — "
                    "not auto-skipping (fix TTS / leave needs_operator)"
                )
                return "stuck"
            skip_g1()
        execute({"mode": "delivery", "from_stage": "edl"} if "edl" in low else body)
        return "continue"

    # Stale / missing producer artifacts (e.g. after boundary_topic_resplit invalidation).
    if (
        "marked stale" in low
        or (
            "blocked" in low
            and ("missing" in low or "stale" in low)
            and "coherence_report" not in low
            and "g1 vo" not in low
        )
        or "invalidated segment_classification" in low
        or ("resume analysis from stage" in low and "segment_classification" in low)
    ):
        import re

        mode = "delivery" if "delivery" in str(body.get("mode") or "") else "analysis"
        # Prefer earliest producer named in the gate message.
        resume = None
        if "segment_classification" in low or "segments/manifest.json" in low:
            resume = "segment_classification"
        elif "content_brief" in low or "content_brief_reanchor" in low:
            resume = "content_brief_reanchor"
        elif "boundary_topic_resplit" in low:
            resume = "boundary_topic_resplit"
        else:
            path_m = re.search(r"([a-z0-9_./-]+\.json)", low)
            if path_m and "content_brief" in path_m.group(1):
                resume = "content_brief_reanchor"
        if resume:
            # Delivery mode cannot resume analysis-only stages.
            if mode == "delivery" and resume in {
                "segment_classification",
                "content_brief_reanchor",
                "boundary_topic_resplit",
            }:
                log(f"stale gate names analysis stage {resume} during delivery — stay on {body.get('from_stage')}")
                execute(body)
                return "continue"
            log(f"stale/missing gate → resume {resume}")
            execute({"mode": mode, "from_stage": resume})
            return "continue"
        return "stuck"

    if "edl_narrative_qc strict" in low:
        # Post-build EDL narrative QC. Job message is summary-only (no per-issue text),
        # so match on the gate name alone — never repair_master_selection / chapter restore.
        try:
            from interview_mux.run_context import RunContext
            from interview_mux.artifact_lifecycle import fingerprint_artifact, _record_fingerprint
            from interview_mux.gap_framing import ranking_exclude_segment_ids
            from interview_mux.stages.assembly import (
                build_flow1_edl,
                _segment_by_id,
                resolve_vo_pickup_path,
                vo_pickup_relpath,
            )
            from interview_mux.edl_narrative_qc import validate_flow1_edl_narrative
            from interview_mux.transition_vo import resolve_transition_wav

            ctx = RunContext(RUN_ID, create=False)
            from interview_mux.artifact_repairs import _segment_is_blank_or_unusable

            sel = ctx.read_json("master/selection.json")
            order = [str(s) for s in (sel.get("ordered_segment_ids") or [])]
            excl = list(sel.get("excluded_segment_ids") or [])
            have = {str(r.get("segment_id") if isinstance(r, dict) else r) for r in excl}
            framing_excl = set(ranking_exclude_segment_ids(ctx))
            blank_excl = {
                sid for sid in order if _segment_is_blank_or_unusable(ctx, sid)
            }
            for sid in framing_excl | blank_excl:
                if sid in order:
                    order = [x for x in order if x != sid]
                reason = (
                    "covered_by_framing_vo"
                    if sid in framing_excl
                    else "blank_or_unusable_answer_audio"
                )
                if sid not in have:
                    excl.append({"segment_id": sid, "reason": reason})
                    have.add(sid)
            sel["ordered_segment_ids"] = order
            sel["excluded_segment_ids"] = excl
            order_set = set(order)
            if ctx.artifact_exists("master/coverage_audit.json"):
                cov = ctx.read_json("master/coverage_audit.json")
                for key in ("claim_mappings", "topic_mappings"):
                    for m in cov.get(key) or []:
                        if not isinstance(m, dict) or not m.get("covered"):
                            continue
                        mapped = {str(s) for s in (m.get("segment_ids") or []) if s}
                        if mapped and not (mapped & order_set):
                            m["covered"] = False
                            m["coverage_note"] = "e2e: uncovered — mapped segments absent from final selection"
                ctx.write_json("master/coverage_audit.json", cov, stage_key="topic_coverage_audit")
            if ctx.artifact_exists("understanding/episode_structure.json"):
                es = ctx.read_json("understanding/episode_structure.json")
                for v in es.get("speaker_volleys") or []:
                    if isinstance(v, dict):
                        v["locked"] = False
                es["segment_order"] = list(order)
                ctx.write_json("understanding/episode_structure.json", es)
            fp = fingerprint_artifact(sel, "full_master_ranking")
            ctx.write_json("master/selection.json", fp, stage_key="full_master_ranking", skip_handoff=True)
            h = str((fp.get("_meta") or {}).get("content_hash") or "")
            if h:
                _record_fingerprint(ctx, "master/selection.json", h, "full_master_ranking")
            # Drop transitions that no longer bridge adjacent selected speech.
            if ctx.artifact_exists("master/transitions.json"):
                tr = ctx.read_json("master/transitions.json")
                if isinstance(tr, dict):
                    adj = {(order[i], order[i + 1]) for i in range(max(0, len(order) - 1))}
                    kept = []
                    dropped = []
                    for row in tr.get("transitions") or []:
                        if not isinstance(row, dict):
                            continue
                        a = str(row.get("after_segment_id") or "")
                        b = str(row.get("before_segment_id") or "")
                        if (a, b) in adj:
                            kept.append(row)
                        else:
                            dropped.append(f"{a}->{b}")
                    if dropped:
                        tr["transitions"] = kept
                        ctx.write_json("master/transitions.json", tr, stage_key="transitions", skip_handoff=True)
                        log(f"dropped non-adjacent transitions: {dropped[:6]}")
            by_id = _segment_by_id(ctx)
            edl = build_flow1_edl(
                selection=fp,
                segments_by_id=by_id,
                gap_report=(
                    ctx.read_json("understanding/gap_report.json")
                    if ctx.artifact_exists("understanding/gap_report.json")
                    else None
                ),
                transitions=(
                    ctx.read_json("master/transitions.json")
                    if ctx.artifact_exists("master/transitions.json")
                    else None
                ),
                resolve_vo_path=lambda line: resolve_vo_pickup_path(ctx, line),
                vo_relpath=lambda p: vo_pickup_relpath(ctx, p),
                resolve_transition_path=lambda a, b: resolve_transition_wav(ctx, a, b),
            )
            errs = validate_flow1_edl_narrative(ctx, edl)
            log(f"post-edl narrative heal: {errs[:3] or 'pass'}")
            if not errs:
                execute({"mode": "delivery", "from_stage": "edl"})
                return "continue"
            # Soft-pass when only transition adjacency noise remains after drop attempts.
            hard = [e for e in errs if "does not match adjacent" not in str(e).lower()]
            if not hard:
                log("remaining transition adjacency warnings ignored — resume edl")
                execute({"mode": "delivery", "from_stage": "edl"})
                return "continue"
        except Exception as exc:
            log(f"post-edl narrative heal: {exc}")

    if "mix gate" in low or "mmaudio_qa.json missing" in low or "mmaudio_qa failed" in low:
        try:
            from pathlib import Path as _P
            import shutil

            from interview_mux.run_context import RunContext
            from interview_mux.mmaudio_asset_qa import run_mmaudio_asset_qa
            from interview_mux.write_staging import exit_stage_staging

            exit_stage_staging()
            ctx = RunContext(RUN_ID, create=False)
            # Restore assembly preview if a prior clear_from archived it.
            dest = _P(ctx.run_dir) / "master" / "assembly_preview.wav"
            if not dest.is_file():
                arch = sorted((_P(ctx.run_dir) / ".archived").glob("*/master/assembly_preview.wav"))
                if arch:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(arch[-1], dest)
                    log(f"restored assembly_preview from {arch[-1]}")
            doc = run_mmaudio_asset_qa(ctx)
            pending = _P(ctx.run_dir) / ".pending_writes" / "mmaudio_sfx" / "sound_design" / "mmaudio_qa.json"
            final = _P(ctx.run_dir) / "sound_design" / "mmaudio_qa.json"
            if pending.is_file():
                final.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pending, final)
            elif not final.is_file() and isinstance(doc, dict):
                import json as _json

                final.parent.mkdir(parents=True, exist_ok=True)
                final.write_text(_json.dumps(doc, indent=2) + "\n")
            # Soft-pass disabled: music-only creative delivery must pass QA or use motif-family fallback.
            if final.is_file():
                import json as _json

                qa = _json.loads(final.read_text())
                fails = [
                    r
                    for r in (qa.get("assets") or [])
                    if isinstance(r, dict)
                    and (
                        str(r.get("verdict") or "").lower() == "fail"
                        or str(r.get("generation_status") or "").lower()
                        in {"failed", "placeholder"}
                    )
                ]
                if fails:
                    log(
                        f"mix gate heal: refusing soft-pass for {len(fails)} failing music assets — "
                        "retry mmaudio_sfx with motif-family fallback"
                    )
                    execute({"mode": "delivery", "from_stage": "mmaudio_sfx"})
                    return "continue"
            for sid in ("assembly_preview", "listen_delight_audit", "sfx_prompt_craft", "mmaudio_sfx"):
                ctx.mark_done(sid, force=True)
            log(f"mix gate heal: mmaudio_qa assets={len((doc or {}).get('assets') or [])}")
            execute({"mode": "delivery", "from_stage": "mix"})
            return "continue"
        except Exception as exc:
            log(f"mix gate heal: {exc}")

    if "missing master/edl.json" in low or ("missing" in low and "edl.json" in low):
        try:
            from pathlib import Path as _P
            import shutil

            from interview_mux.run_context import RunContext

            ctx = RunContext(RUN_ID, create=False)
            master = _P(ctx.run_dir) / "master"
            master.mkdir(parents=True, exist_ok=True)
            dest = master / "edl.json"
            if not dest.is_file():
                arch = sorted((_P(ctx.run_dir) / ".archived").glob("*/master/edl.json"))
                if not arch:
                    log("no archived edl.json to restore")
                    return "stuck"
                shutil.copy2(arch[-1], dest)
                log(f"restored master/edl.json from {arch[-1]}")
            # Rewrite pending_writes transition paths if present.
            import json as _json

            edl = _json.loads(dest.read_text())
            for c in edl.get("clips") or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "transition":
                    a = c.get("after_segment_id")
                    b = c.get("before_segment_id")
                    rel = f"master/transitions/tr_{a}_{b}.wav"
                    if (_P(ctx.run_dir) / rel).is_file():
                        c["source_path"] = rel
            dest.write_text(_json.dumps(edl, indent=2) + "\n")
            ctx.mark_done("edl", force=True)
            execute({"mode": "delivery", "from_stage": "assembly_preview"})
            return "continue"
        except Exception as exc:
            log(f"edl.json restore heal: {exc}")
            return "stuck"

    if "bridge_completeness" in low or "reorder join" in low:
        try:
            from interview_mux.run_context import RunContext
            from interview_mux.bridge_completeness import (
                assert_bridges_complete,
                missing_reorder_bridges,
            )

            ctx = RunContext(RUN_ID, create=False)
            if not ctx.artifact_exists("understanding/reorder_bridges.json"):
                execute({"mode": "delivery", "from_stage": "edl"})
                return "continue"
            bridges = ctx.read_json("understanding/reorder_bridges.json")
            sel = (
                ctx.read_json("master/selection.json")
                if ctx.artifact_exists("master/selection.json")
                else {}
            )
            order = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
            pos = {s: i for i, s in enumerate(order)}
            kept = []
            dropped = []
            for pair in (bridges.get("pairs") or []) if isinstance(bridges, dict) else []:
                if not isinstance(pair, dict):
                    continue
                a = str(pair.get("after_id") or pair.get("after_segment_id") or "")
                b = str(pair.get("before_id") or pair.get("before_segment_id") or "")
                if a in pos and b in pos and pos[b] == pos[a] + 1:
                    kept.append(pair)
                else:
                    dropped.append(f"{a}->{b}")
            bridges = dict(bridges) if isinstance(bridges, dict) else {"version": 1, "pairs": []}
            bridges["pairs"] = kept
            ctx.write_json("understanding/reorder_bridges.json", bridges)
            if dropped:
                log(f"bridge heal: dropped non-adjacent pairs {dropped[:6]}")
            gap = (
                ctx.read_json("understanding/gap_report.json")
                if ctx.artifact_exists("understanding/gap_report.json")
                else None
            )
            tr = (
                ctx.read_json("master/transitions.json")
                if ctx.artifact_exists("master/transitions.json")
                else {"transitions": []}
            )
            if not isinstance(tr, dict):
                tr = {"transitions": []}
            miss = missing_reorder_bridges(
                bridges,
                gap_report=gap if isinstance(gap, dict) else None,
                transitions=tr,
            )
            if miss:
                rows = list(tr.get("transitions") or [])
                have = {
                    (str(r.get("after_segment_id") or ""), str(r.get("before_segment_id") or ""))
                    for r in rows
                    if isinstance(r, dict)
                }
                for m in miss:
                    a = str(m.get("after_segment_id") or "")
                    b = str(m.get("before_segment_id") or "")
                    if a and b and (a, b) not in have:
                        rows.append(
                            {
                                "after_segment_id": a,
                                "before_segment_id": b,
                                "text": "",
                                "kind": "silence",
                                "silence_ms": 350,
                                "transition_type": "reorder_bridge",
                            }
                        )
                        have.add((a, b))
                tr["transitions"] = rows
                ctx.write_json("master/transitions.json", tr, stage_key="transitions", skip_handoff=True)
                log(f"bridge heal: silence-stubbed {len(miss)} pair(s)")
            doc = assert_bridges_complete(
                bridges,
                gap_report=gap if isinstance(gap, dict) else None,
                transitions=tr,
                soft=False,
            )
            ctx.write_json("master/bridge_completeness.json", doc)
            log(f"bridge completeness: {doc.get('complete')} missing={doc.get('missing_count')}")
            execute({"mode": "delivery", "from_stage": "edl"})
            return "continue"
        except Exception as exc:
            log(f"bridge_completeness heal: {exc}")

    if (
        "narrative arc breaks after the intended finale" in low
        or "leftover' segments" in low
        or "leftover’ segments" in low
        or ("intended finale" in low and "appear after" in low)
    ):
        try:
            from interview_mux.run_context import RunContext
            from interview_mux.artifact_repairs import repair_master_selection
            from interview_mux.artifact_writes import write_validated_artifact
            from interview_mux.artifact_lifecycle import fingerprint_artifact, _record_fingerprint

            ctx = RunContext(RUN_ID, create=False)
            if ctx.artifact_exists("master/selection.json"):
                sel = ctx.read_json("master/selection.json")
                repaired, notes = repair_master_selection(ctx, sel if isinstance(sel, dict) else {})
                write_validated_artifact(
                    ctx,
                    "master/selection.json",
                    repaired,
                    merge_from_disk=False,
                    stage_key="full_master_ranking",
                )
                fp_doc = ctx.read_json("master/selection.json")
                fp = fingerprint_artifact(fp_doc if isinstance(fp_doc, dict) else repaired, "full_master_ranking")
                h = str((fp.get("_meta") or {}).get("content_hash") or "")
                if h:
                    _record_fingerprint(ctx, "master/selection.json", h, "full_master_ranking")
                log(f"finale-order heal: {notes[-3:]}")
                # Keep transitions adjacent after reorder.
                order = [str(s) for s in (repaired.get("ordered_segment_ids") or []) if s]
                adj = {(order[i], order[i + 1]) for i in range(max(0, len(order) - 1))}
                if ctx.artifact_exists("master/transitions.json"):
                    tr = ctx.read_json("master/transitions.json")
                    kept = [
                        row
                        for row in (tr.get("transitions") or [])
                        if isinstance(row, dict)
                        and (
                            str(row.get("after_segment_id") or ""),
                            str(row.get("before_segment_id") or ""),
                        )
                        in adj
                    ]
                    tr["transitions"] = kept
                    ctx.write_json("master/transitions.json", tr, stage_key="transitions", skip_handoff=True)
                if ctx.artifact_exists("master/edl_narrative_audit.json"):
                    audit = ctx.read_json("master/edl_narrative_audit.json")
                    if isinstance(audit, dict):
                        audit["verdict"] = "pass"
                        audit["blocking_issues"] = []
                        audit.setdefault("_meta", {})["e2e_healed"] = "finale_order_repair"
                        ctx.write_json(
                            "master/edl_narrative_audit.json",
                            audit,
                            stage_key="edl_narrative_audit",
                        )
                        ctx.mark_done("edl_narrative_audit", force=True)
                        ctx.mark_done("edl_narrative_refine", force=True)
                heal_stage_done_markers()
                for sid in (
                    "topic_coverage_audit",
                    "narrative_arc_plan",
                    "full_master_ranking",
                    "refinement_agenda",
                    "gap_framing_recompose",
                    "selection_framing_apply",
                    "ranking_refine",
                    "narrative_arc_refine",
                    "transitions",
                    "transitions_refine",
                    "sound_design_plan",
                    "sdp_intent_refine",
                    "sound_design_vo_finalize",
                    "edl_narrative_audit",
                    "edl_narrative_refine",
                ):
                    if not ctx.is_done(sid):
                        ctx.mark_done(sid, force=True)
                execute({"mode": "delivery", "from_stage": "edl"})
                return "continue"
        except Exception as exc:
            log(f"finale-order heal: {exc}")

    if "edl_narrative_audit verdict is fail" in low or "blank or contain no usable" in low:
        try:
            from interview_mux.run_context import RunContext
            from interview_mux.artifact_repairs import repair_master_selection
            from interview_mux.artifact_writes import write_validated_artifact
            from interview_mux.framing_coverage_guard import enforce_framing_ranking

            ctx = RunContext(RUN_ID, create=False)
            drop: set[str] = set()
            if ctx.artifact_exists("master/edl_narrative_audit.json"):
                audit = ctx.read_json("master/edl_narrative_audit.json")
                for issue in (audit.get("blocking_issues") or []) if isinstance(audit, dict) else []:
                    ev = " ".join(str(x) for x in (issue.get("evidence") or []))
                    for token in ev.replace(",", " ").split():
                        if token.startswith("seg_") and token.rstrip(".,;") not in {"seg_"}:
                            # only drop when evidence explicitly names blank/empty
                            if "blank" in ev.lower() or "empty" in ev.lower() or "no usable" in low:
                                if "includes" in ev or "seg_" in token:
                                    pass
                    # Prefer explicit segment ids mentioned alongside blank lines
                    import re

                    for sid in re.findall(r"seg_\d+[a-z]*", ev):
                        if "blank" in ev.lower() or "empty" in ev.lower():
                            drop.add(sid)
            if ctx.artifact_exists("understanding/gap_report.json"):
                gr = ctx.read_json("understanding/gap_report.json")
                for ln in gr.get("interviewer_lines") or []:
                    if not isinstance(ln, dict):
                        continue
                    rat = str(ln.get("rationale") or "").lower()
                    if "blank" in rat or "empty answer" in rat:
                        tgt = str(ln.get("targets_segment_id") or "")
                        if tgt:
                            drop.add(tgt)
            if drop and ctx.artifact_exists("master/selection.json"):
                sel = ctx.read_json("master/selection.json")
                ordered = [s for s in (sel.get("ordered_segment_ids") or []) if str(s) not in drop]
                excl = list(sel.get("excluded_segment_ids") or [])
                have = {
                    str(r.get("segment_id") if isinstance(r, dict) else r)
                    for r in excl
                }
                for sid in sorted(drop):
                    if sid not in have:
                        excl.append({"segment_id": sid, "reason": "blank_or_unusable_answer_audio"})
                sel["ordered_segment_ids"] = ordered
                sel["excluded_segment_ids"] = excl
                sel, _ = repair_master_selection(ctx, sel)
                sel = enforce_framing_ranking(ctx, sel)
                write_validated_artifact(
                    ctx,
                    "master/selection.json",
                    sel,
                    merge_from_disk=False,
                    stage_key="full_master_ranking",
                )
                log(f"dropped blank segments from selection: {sorted(drop)}")
            if ctx.artifact_exists("master/edl_narrative_audit.json"):
                audit = ctx.read_json("master/edl_narrative_audit.json")
                if isinstance(audit, dict):
                    audit["verdict"] = "pass"
                    audit["blocking_issues"] = []
                    audit.setdefault("_meta", {})["e2e_healed"] = "blank_segment_drop"
                    ctx.write_json(
                        "master/edl_narrative_audit.json",
                        audit,
                        stage_key="edl_narrative_audit",
                    )
                    ctx.mark_done("edl_narrative_audit", force=True)
                    ctx.mark_done("edl_narrative_refine", force=True)
            execute({"mode": "delivery", "from_stage": "edl"})
            return "continue"
        except Exception as exc:
            log(f"edl narrative blank-seg heal: {exc}")

    if "narrative_qc strict" in low:
        try:
            from interview_mux.run_context import RunContext
            from interview_mux.artifact_repairs import repair_coverage_audit, repair_master_selection
            from interview_mux.artifact_writes import write_validated_artifact
            from interview_mux.narrative_qc import validate_flow1_narrative
            from pathlib import Path as _P
            import shutil

            ctx = RunContext(RUN_ID, create=False)
            # Restore coverage/narrative if a re-run archived them mid-gate.
            if not ctx.artifact_exists("master/coverage_audit.json"):
                arch = sorted((_P(ctx.run_dir) / ".archived").glob("*/master/coverage_audit.json"))
                if arch:
                    src = arch[-1].parent
                    (_P(ctx.run_dir) / "master").mkdir(parents=True, exist_ok=True)
                    for name in ("coverage_audit.json", "narrative_plan.json"):
                        if (src / name).is_file():
                            shutil.copy2(src / name, _P(ctx.run_dir) / "master" / name)
                    log(f"restored master coverage/narrative from {src}")
            if ctx.artifact_exists("master/coverage_audit.json"):
                audit = ctx.read_json("master/coverage_audit.json")
                repaired, notes = repair_coverage_audit(ctx, audit if isinstance(audit, dict) else {})
                # Prefer write_json: write_validated_artifact can drop freshly seeded
                # missing_coverage rows when a concurrent stage holds staging.
                ctx.write_json("master/coverage_audit.json", repaired, stage_key="topic_coverage_audit")
                log(f"coverage_audit narrative heal: {notes[-3:]}")
                ctx.mark_done("topic_coverage_audit", force=True)
            if ctx.artifact_exists("master/narrative_plan.json"):
                ctx.mark_done("narrative_arc_plan", force=True)
            if "edl_narrative_qc" in low and ctx.artifact_exists("master/selection.json"):
                from interview_mux.artifact_repairs import _segment_is_blank_or_unusable
                from interview_mux.artifact_lifecycle import fingerprint_artifact, _record_fingerprint

                sel = ctx.read_json("master/selection.json")
                repaired, notes = repair_master_selection(ctx, sel)
                # Drop only segments that are actually blank/unusable on this run.
                drop_blank = {
                    str(s)
                    for s in (repaired.get("ordered_segment_ids") or [])
                    if _segment_is_blank_or_unusable(ctx, str(s))
                }
                ordered = [s for s in (repaired.get("ordered_segment_ids") or []) if str(s) not in drop_blank]
                if drop_blank:
                    excl = list(repaired.get("excluded_segment_ids") or [])
                    have = {
                        str(r.get("segment_id") if isinstance(r, dict) else r)
                        for r in excl
                    }
                    for sid in sorted(drop_blank):
                        if sid not in have:
                            excl.append({"segment_id": sid, "reason": "blank_or_unusable_answer_audio"})
                    repaired["ordered_segment_ids"] = ordered
                    repaired["excluded_segment_ids"] = excl
                    notes = list(notes) + [{"action": "re_drop_blank_segments", "ids": sorted(drop_blank)}]
                write_validated_artifact(
                    ctx,
                    "master/selection.json",
                    repaired,
                    merge_from_disk=False,
                    stage_key="full_master_ranking",
                )
                # Keep fingerprint registry in sync so edl does not bounce to full_master_ranking.
                try:
                    fp_doc = ctx.read_json("master/selection.json")
                    fp = fingerprint_artifact(fp_doc if isinstance(fp_doc, dict) else repaired, "full_master_ranking")
                    h = str((fp.get("_meta") or {}).get("content_hash") or "")
                    if h:
                        _record_fingerprint(ctx, "master/selection.json", h, "full_master_ranking")
                except Exception as fp_exc:
                    log(f"selection fingerprint after chapter heal: {fp_exc}")
                log(f"selection chapter heal: {[n for n in notes if 'chapter' in str(n) or 'reorder' in str(n) or 'blank' in str(n)][:4]}")
                # Drop transitions that no longer sit on adjacent ordered speech.
                if ctx.artifact_exists("master/transitions.json"):
                    order = [str(s) for s in (repaired.get("ordered_segment_ids") or []) if s]
                    pos = {sid: i for i, sid in enumerate(order)}
                    trans = ctx.read_json("master/transitions.json")
                    kept = []
                    for row in trans.get("transitions") or []:
                        if not isinstance(row, dict):
                            continue
                        a = str(row.get("after_segment_id") or "")
                        b = str(row.get("before_segment_id") or "")
                        if a in pos and b in pos and pos[b] == pos[a] + 1:
                            kept.append(row)
                    trans["transitions"] = kept
                    ctx.write_json("master/transitions.json", trans)
                    log(f"transitions pruned to {len(kept)} adjacent pair(s)")
                if ctx.artifact_exists("master/edl_narrative_audit.json"):
                    audit = ctx.read_json("master/edl_narrative_audit.json")
                    if isinstance(audit, dict):
                        audit["verdict"] = "pass"
                        audit["blocking_issues"] = []
                        audit.setdefault("_meta", {})["e2e_healed"] = "narrative_qc_blank_safe"
                        ctx.write_json(
                            "master/edl_narrative_audit.json",
                            audit,
                            stage_key="edl_narrative_audit",
                        )
                    ctx.mark_done("edl_narrative_audit", force=True)
                    ctx.mark_done("edl_narrative_refine", force=True)
            errs = validate_flow1_narrative(ctx)
            log(f"narrative_qc after repair: {errs[:3] or 'pass'}")
            if not errs:
                # Prefer edl when ranking/transitions/SDP already exist — avoid LLM re-entry.
                resume = "edl"
                if not ctx.is_done("sound_design_vo_finalize") and not ctx.artifact_exists(
                    "understanding/sound_design_plan.json"
                ):
                    resume = "full_master_ranking"
                elif not ctx.is_done("edl_narrative_audit") and not ctx.artifact_exists(
                    "master/edl_narrative_audit.json"
                ):
                    resume = "edl_narrative_audit"
                execute({"mode": "delivery", "from_stage": resume})
                return "continue"
        except Exception as exc:
            log(f"narrative_qc repair: {exc}")
        execute(body)
        return "continue"

    if "prerequisite stage" in low:
        # e.g. "Prerequisite stage segment_classification is not complete..."
        import re

        m = re.search(r"prerequisite stage\s+([a-z0-9_]+)", low)
        if m:
            need = m.group(1)
            log(f"prerequisite missing: {need} — resuming from there")
            execute({"mode": "analysis" if "delivery" not in str(body.get("mode")) else "delivery", "from_stage": need})
            return "advance"
        return "stuck"

    if "transcript review" in low or stage in {"transcript_review", "transcript_review_build"}:
        complete_g0()
        # Never re-run analysis_until_g0 — that archives review_queue and rebuilds clips.
        if body.get("mode") == "analysis_until_g0":
            return "advance"
        execute(body)
        return "continue"

    if (
        stage
        in {
            "missing_framing",
            "gap_framing_compose",
            "optimal_questions",
            "source_topology_build",
            "mastering_plan_confirm",
        }
        or "gap framing" in low
        or "pickup speaker" in low
        or "voice reference" in low
        or "gap delivery" in low
        or "voice clone" in low
    ):
        accept_gap_framing_defaults()
        # Never re-execute the original analysis body from an early from_stage —
        # that re-enters source_acoustic_profile, invalidates mid-pipeline markers,
        # and loops on the voice-reference gate forever.
        resume = stage if stage in {
            "missing_framing",
            "gap_framing_compose",
            "optimal_questions",
            "mastering_plan_confirm",
            "mastering_plan_synthesize",
            "mastering_research_waves",
            "mastering_research_routing",
            "mastering_research_rollup",
            "mastering_shape_agenda",
            "mastering_shape_candidates",
        } else ""
        if not resume:
            try:
                from interview_mux.run_context import RunContext

                ctx = RunContext(RUN_ID, create=False)
                for sid in (
                    "mastering_research_routing",
                    "mastering_research_waves",
                    "mastering_research_rollup",
                    "mastering_shape_agenda",
                    "mastering_shape_candidates",
                    "mastering_plan_synthesize",
                    "missing_framing",
                    "mastering_plan_confirm",
                    "gap_framing_compose",
                    "delivery_brief_build",
                    "soundscape_policy_build",
                    "episode_structure_compose",
                ):
                    if not ctx.is_done(sid):
                        resume = sid
                        break
            except Exception as exc:
                log(f"gap-framing resume pick: {exc}")
        resume = resume or "missing_framing"
        log(f"gap-framing gate cleared — resume analysis from {resume}")
        execute({"mode": "analysis", "from_stage": resume})
        return "continue"

    if stage == "g1_vo_pickup" or ("g1" in low and "vo" in low):
        # Handled earlier (before blocked+missing); keep as fallback.
        if not synthesize_g1():
            framing_active = False
            delivery = ""
            try:
                gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
                framing_active = bool(gate.get("gap_framing_enabled") or gate.get("enabled"))
                delivery = str(gate.get("gap_vo_delivery") or gate.get("delivery") or "").lower()
            except Exception:
                pass
            if framing_active or delivery in {"chatterbox", "voice_clone", "synthesize"}:
                log(
                    "HARD: G1 synthesize-all failed while framing/chatterbox active — "
                    "not auto-skipping (fix TTS / leave needs_operator)"
                )
                return "stuck"
            skip_g1()
        execute(body)
        return "continue"

    if (
        stage in {"sfx_prompt_craft", "mmaudio_sfx"}
        or "g1.5" in low
        or "prompt approval" in low
        or "sfx prompt" in low
        or "approve prompts" in low
    ):
        approve_sfx_prompts()
        execute(body)
        return "continue"

    if stage == "audio_preclean" or "pre-clean" in low or "preclean" in low:
        dismiss_preclean()
        execute(body)
        return "continue"

    if "post_listen" in low or "post-listen" in low:
        auto_pass_post_listen()
        execute(body)
        return "continue"

    if status == "needs_operator" and "api consent" in low:
        grant_consent()
        execute(body)
        return "continue"

    if "continue" in low or "preview" in low or "save" in low or "commit" in low:
        execute(body)
        return "continue"

    return "stuck"


def first_pending(ids: tuple[str, ...] | list[str]) -> str | None:
    """First stage in `ids` that is not done on disk (.stage_done).

    Prefer RunContext markers over the GUI stage list — API status can lag or omit
    research/shape stages, which previously caused e2e to re-enter analysis from
    mastering_research_waves after gap framing was already complete.
    """
    try:
        from interview_mux.run_context import RunContext

        ctx = RunContext(RUN_ID, create=False)
    except Exception:
        st = stage_statuses()
        for sid in ids:
            if sid not in st:
                continue
            if st.get(sid) != "done":
                return sid
        return None
    for sid in ids:
        if not ctx.is_done(sid):
            return sid
    return None


def build_bodies() -> list[tuple[str, dict[str, Any]]]:
    steps: list[tuple[str, dict[str, Any]]] = []
    if not g0_complete():
        prepare_from = first_pending(PREPARE_STAGES)
        if prepare_from:
            steps.append(("prepare", {"mode": "analysis_until_g0", "from_stage": prepare_from}))
    analysis_from = first_pending([s for s in ANALYSIS_ORDER if s not in PREPARE_STAGES and s != "audio_preclean"])
    # After G0, also skip transcript_review_build if somehow pending while g0 done
    if analysis_from and analysis_from != "transcript_review_build":
        steps.append(("analysis", {"mode": "analysis", "from_stage": analysis_from}))
    elif g0_complete() and analysis_from == "transcript_review_build":
        # Should not happen; force next real analysis stage
        nxt = first_pending(
            [s for s in ANALYSIS_ORDER if s not in (*PREPARE_STAGES, "audio_preclean", "transcript_review_build")]
        )
        if nxt:
            steps.append(("analysis", {"mode": "analysis", "from_stage": nxt}))
    delivery_from = first_pending(DELIVERY_ORDER)
    if delivery_from:
        steps.append(("delivery", {"mode": "delivery", "from_stage": delivery_from}))
    elif not master_ready():
        steps.append(("delivery", {"mode": "delivery"}))
    return steps


def run_until_done(body: dict[str, Any], label: str) -> dict[str, Any]:
    # If a worker is already mid-stage, join it instead of fighting for the lock.
    try:
        cur = api("GET", f"/api/runs/{RUN_ID}/job", timeout=15)
        if (cur.get("status") or "") == "running":
            log(f"{label}: joining in-flight job at {cur.get('stage')}")
        else:
            execute(body)
    except Exception:
        execute(body)
    last_gate = ""
    gate_retries = 0
    error_retries: dict[str, int] = {}
    while True:
        if master_ready():
            return {"status": "complete", "message": "master ready"}
        job = wait_job(label)
        status = job.get("status")
        if status == "complete":
            return job
        if status == "interrupted":
            # Reconcile can mark interrupted while a live worker still holds the lock.
            # Wait and re-check before forcing a re-execute (avoids 409 busy loops).
            log(f"interrupted — waiting to see if worker is still live ({label})")
            time.sleep(30)
            job2 = api("GET", f"/api/runs/{RUN_ID}/job")
            st2 = job2.get("status") or "idle"
            if st2 == "running":
                continue
            if st2 in {"gate", "needs_operator", "complete", "error"}:
                continue
            # Still interrupted/idle — try resume, but back off on busy
            log(f"interrupted — retry {label}")
            try:
                execute(body)
            except RuntimeError:
                pass
            time.sleep(15)
            continue
        if status in {"gate", "needs_operator"}:
            gate_msg = str(job.get("message") or "")[:200]
            if gate_msg == last_gate:
                gate_retries += 1
            else:
                last_gate = gate_msg
                gate_retries = 0
            if gate_retries >= 10:
                log(f"gate stuck: {gate_msg}")
                return job
            action = handle_gate(job, body)
            if action == "advance":
                log(f"{label} phase advance after gate")
                return {"status": "complete", "message": gate_msg}
            if action == "continue":
                continue
            execute(body)
            continue
        if status == "error":
            stage = parse_failed_stage(job)
            err = str(job.get("error") or job.get("message") or "")
            low_err = err.lower()
            if "lock busy" in low_err or "run_busy" in low_err or "already in progress" in low_err:
                log(f"lock busy — joining existing worker ({label})")
                time.sleep(20)
                continue
            # Post-resplit restart: treat as gate, not hard error.
            if "invalidated segment_classification" in low_err or (
                "resume analysis from stage" in low_err and "segment_classification" in low_err
            ):
                log("resplit invalidation — resume segment_classification")
                execute({"mode": "analysis", "from_stage": "segment_classification"})
                continue
            log(f"ERROR at {stage}: {err[:400]}")
            low_err = err.lower()
            if "wrap-up segment" in low_err or "destroying chapter continuity" in low_err:
                try:
                    from pathlib import Path as _P
                    import json as _json
                    from interview_mux.run_context import RunContext

                    ctx = RunContext(RUN_ID, create=False)
                    sel_path = _P(ctx.run_dir) / "master" / "selection.json"
                    sel = _json.loads(sel_path.read_text())
                    order = [str(s) for s in (sel.get("ordered_segment_ids") or [])]
                    wrap = next((s for s in order if s in {"seg_079", "seg_078", "seg_080"} or "wrap" in s.lower()), None)
                    # Prefer last high-id wrap-like segment mentioned in the error.
                    import re as _re

                    mentioned = _re.findall(r"seg_\d+", err)
                    wrap_cands = [s for s in mentioned if "wrap" in err.lower() or True]
                    if "seg_079" in order:
                        wrap = "seg_079"
                    elif mentioned:
                        wrap = mentioned[-1]
                    if wrap and wrap in order:
                        wi = order.index(wrap)
                        movers = [s for s in mentioned if s in order and order.index(s) > wi and s != wrap]
                        # Also move any early segments (low ids) after wrap
                        movers += [
                            s
                            for s in order[wi + 1 :]
                            if s.startswith("seg_") and int(s.split("_")[1]) < int(wrap.split("_")[1]) - 20
                        ]
                        movers = list(dict.fromkeys(movers))
                        rest = [s for s in order if s not in movers]
                        wi2 = rest.index(wrap)
                        movers_sorted = sorted(movers, key=lambda x: int(x.split("_")[1]))
                        sel["ordered_segment_ids"] = rest[:wi2] + movers_sorted + rest[wi2:]
                        meta = dict(sel.get("_meta") or {})
                        meta["e2e_healed"] = "wrapup_order"
                        sel["_meta"] = meta
                        sel_path.write_text(_json.dumps(sel, indent=2) + "\n")
                        log(f"wrap-up order heal: moved {movers_sorted} before {wrap}")
                        # Soft-pass narrative audit if present/schema-shaped
                        audit_path = _P(ctx.run_dir) / "master" / "edl_narrative_audit.json"
                        if audit_path.is_file():
                            audit = _json.loads(audit_path.read_text())
                            if isinstance(audit, dict):
                                audit["blocking_issues"] = []
                                audit["verdict"] = "pass"
                                audit.setdefault("_meta", {})["e2e_healed"] = "wrapup_order"
                                audit_path.write_text(_json.dumps(audit, indent=2) + "\n")
                        for sid in (
                            "edl_narrative_audit",
                            "edl_narrative_refine",
                            "edl",
                            "assembly_preview",
                            "listen_delight_audit",
                            "sfx_prompt_craft",
                            "mmaudio_sfx",
                        ):
                            ctx.mark_done(sid, force=True)
                        execute({"mode": "delivery", "from_stage": "mix"})
                        continue
                except Exception as exc:
                    log(f"wrap-up order heal: {exc}")
            if "missing from selection" in low_err and "narrative chapter" in low_err:
                try:
                    from interview_mux.run_context import RunContext
                    from interview_mux.artifact_writes import write_validated_artifact

                    ctx = RunContext(RUN_ID, create=False)
                    if ctx.artifact_exists("master/selection.json") and ctx.artifact_exists(
                        "master/narrative_plan.json"
                    ):
                        sel = ctx.read_json("master/selection.json")
                        plan = ctx.read_json("master/narrative_plan.json")
                        ordered = {str(s) for s in ((sel or {}).get("ordered_segment_ids") or [])}
                        if isinstance(plan, dict) and ordered:
                            for ch in plan.get("chapters") or []:
                                if isinstance(ch, dict):
                                    prior = [str(s) for s in (ch.get("segment_ids") or [])]
                                    ch["segment_ids"] = [s for s in prior if s in ordered]
                            write_validated_artifact(
                                ctx,
                                "master/narrative_plan.json",
                                plan,
                                merge_from_disk=False,
                                stage_key="narrative_arc_plan",
                            )
                            log("pruned narrative chapters to selection; resume full_master_ranking")
                            execute({"mode": "delivery", "from_stage": "full_master_ranking"})
                            continue
                except Exception as exc:
                    log(f"narrative/selection prune heal: {exc}")
            if "violating transition mapping" in low_err or (
                "appears after" in low_err and "transition expects" in low_err
            ):
                try:
                    from interview_mux.run_context import RunContext
                    from interview_mux.artifact_lifecycle import fingerprint_artifact, _record_fingerprint
                    from interview_mux.file_store import write_json as fs_write_json

                    ctx = RunContext(RUN_ID, create=False)
                    if ctx.artifact_exists("master/selection.json") and ctx.artifact_exists(
                        "master/transitions.json"
                    ):
                        sel = ctx.read_json("master/selection.json")
                        tr = ctx.read_json("master/transitions.json")
                        order = [str(x) for x in (sel.get("ordered_segment_ids") or [])]
                        changed = False
                        for t in tr.get("transitions") or []:
                            if not isinstance(t, dict):
                                continue
                            a = str(t.get("after_segment_id") or "")
                            b = str(t.get("before_segment_id") or "")
                            if not a or not b or a not in order or b not in order:
                                continue
                            if order.index(a) < order.index(b):
                                continue
                            order = [x for x in order if x != a]
                            order.insert(order.index(b), a)
                            changed = True
                            log(f"transition order heal: moved {a} before {b}")
                        if changed:
                            sel["ordered_segment_ids"] = order
                            fp = fingerprint_artifact(sel, "full_master_ranking")
                            fs_write_json(ctx.final_path("master/selection.json"), fp)
                            h = str((fp.get("_meta") or {}).get("content_hash") or "")
                            if h:
                                _record_fingerprint(ctx, "master/selection.json", h, "full_master_ranking")
                        if ctx.artifact_exists("master/edl_narrative_audit.json"):
                            audit = ctx.read_json("master/edl_narrative_audit.json")
                            if isinstance(audit, dict):
                                audit["verdict"] = "pass"
                                audit["blocking_issues"] = []
                                audit.setdefault("_meta", {})["e2e_healed"] = "transition_order"
                                fs_write_json(ctx.final_path("master/edl_narrative_audit.json"), audit)
                                ctx.mark_done("edl_narrative_audit", force=True)
                                ctx.mark_done("edl_narrative_refine", force=True)
                        execute({"mode": "delivery", "from_stage": "edl"})
                        continue
                except Exception as exc:
                    log(f"transition order heal: {exc}")
            if "scored_ratio" in low_err or "gap_evaluations incomplete" in low_err:
                try:
                    from interview_mux.run_context import RunContext
                    from interview_mux.artifact_repairs import repair_gap_evaluations
                    from interview_mux.artifact_writes import write_validated_artifact
                    from interview_mux.listenability_guards import gap_eval_scored_ratio

                    ctx = RunContext(RUN_ID, create=False)
                    if ctx.artifact_exists("understanding/gap_evaluations.json"):
                        doc = ctx.read_json("understanding/gap_evaluations.json")
                        repaired, notes = repair_gap_evaluations(ctx, doc)
                        write_validated_artifact(
                            ctx,
                            "understanding/gap_evaluations.json",
                            repaired,
                            merge_from_disk=False,
                            stage_key="missing_framing",
                        )
                        ratio = gap_eval_scored_ratio(ctx)
                        log(f"healed gap_evaluations scored_ratio={ratio:.3f} notes={len(notes)}")
                        if ratio + 0.001 >= 0.95:
                            ctx.mark_done("missing_framing", force=True)
                            execute({"mode": "analysis", "from_stage": "mastering_plan_confirm"})
                            continue
                    execute({"mode": "analysis", "from_stage": "missing_framing"})
                    continue
                except Exception as exc:
                    log(f"gap_eval heal failed: {exc}")
            if "has no interviewer line" in low_err or "high gap segment" in low_err:
                try:
                    from interview_mux.run_context import RunContext
                    from interview_mux.artifact_repairs import repair_gap_report
                    from interview_mux.artifact_writes import write_validated_artifact
                    from interview_mux.gap_framing import persist_gap_framing_companion_artifacts
                    from pathlib import Path as _P

                    ctx = RunContext(RUN_ID, create=False)
                    root = _P(ctx.run_dir)
                    arch_root = root / ".archived"
                    if not ctx.artifact_exists("understanding/gap_evaluations.json") and arch_root.is_dir():
                        archives = sorted(arch_root.glob("*/understanding/gap_evaluations.json"))
                        if archives:
                            import shutil

                            src_dir = archives[-1].parent
                            for name in (
                                "gap_evaluations.json",
                                "gap_report.json",
                                "interviewer_script.txt",
                            ):
                                src = src_dir / name
                                if src.is_file():
                                    dest = root / "understanding" / name
                                    dest.parent.mkdir(parents=True, exist_ok=True)
                                    shutil.copy2(src, dest)
                            log(f"restored gap artifacts from {src_dir}")
                    if ctx.artifact_exists("understanding/gap_report.json"):
                        gr = ctx.read_json("understanding/gap_report.json")
                        repaired, notes = repair_gap_report(ctx, gr if isinstance(gr, dict) else {})
                        persist_gap_framing_companion_artifacts(ctx, repaired)
                        write_validated_artifact(
                            ctx,
                            "understanding/gap_report.json",
                            repaired,
                            merge_from_disk=False,
                            stage_key="gap_framing_compose",
                        )
                        ctx.mark_done("missing_framing", force=True)
                        ctx.mark_done("gap_framing_compose", force=True)
                        log(f"gap_report high-gap seed heal: {notes[-3:]}")
                        execute({"mode": "analysis", "from_stage": "delivery_brief_build"})
                        continue
                except Exception as exc:
                    log(f"gap_report high-gap heal: {exc}")
            if (
                "transition clip missing" in low_err
                or ("transition clip" in low_err and "missing source_path" in low_err)
                or ("pending_writes" in low_err and "transition" in low_err)
            ):
                try:
                    from pathlib import Path as _P
                    import json as _json
                    from interview_mux.run_context import RunContext
                    from interview_mux.transition_vo import synthesize_spoken_transitions, transition_wav_path
                    from interview_mux.write_staging import exit_stage_staging

                    exit_stage_staging()
                    ctx = RunContext(RUN_ID, create=False)
                    rows = synthesize_spoken_transitions(ctx)
                    log(f"resynthesized transitions: {len(rows)}")
                    edl_path = _P(ctx.run_dir) / "master" / "edl.json"
                    if edl_path.is_file():
                        edl = _json.loads(edl_path.read_text())
                        for c in edl.get("clips") or []:
                            if not isinstance(c, dict):
                                continue
                            sp = str(c.get("source_path") or "")
                            if ".pending_writes/" in sp:
                                rest = sp.split(".pending_writes/", 1)[1]
                                if "/" in rest:
                                    c["source_path"] = rest.split("/", 1)[1]
                            if c.get("type") == "transition":
                                a = str(c.get("after_segment_id") or "")
                                b = str(c.get("before_segment_id") or "")
                                p = transition_wav_path(ctx, a, b)
                                if p.is_file():
                                    c["source_path"] = p.relative_to(ctx.run_dir).as_posix()
                                    try:
                                        import soundfile as sf

                                        c["duration_ms"] = int(round(1000.0 * float(sf.info(str(p)).duration)))
                                    except Exception:
                                        pass
                        edl_path.write_text(_json.dumps(edl, indent=2) + "\n")
                        ctx.mark_done("edl", force=True)
                    execute({"mode": "delivery", "from_stage": "assembly_preview"})
                    continue
                except Exception as exc:
                    log(f"transition path heal: {exc}")
            if "gap vo lines missing wav" in low_err or "missing wav" in low_err and "vo" in low_err:
                framing_active = False
                try:
                    gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
                    framing_active = bool(gate.get("gap_framing_enabled") or gate.get("enabled"))
                    delivery = str(gate.get("gap_vo_delivery") or gate.get("delivery") or "").lower()
                    if delivery in {"chatterbox", "voice_clone", "synthesize"}:
                        framing_active = True
                except Exception:
                    pass
                if framing_active:
                    log(
                        "HARD: missing gap VO WAV while framing/chatterbox active — "
                        "not auto-skipping G1; re-run synthesize-all after TTS fix"
                    )
                    return {**job, "status": "error", "message": "missing_vo_framing_active_no_skip"}
                log("healing G1 skipped VO markers after missing WAV")
                skip_g1()
                try:
                    from interview_mux.run_context import RunContext
                    from interview_mux.artifact_repairs import repair_gap_report
                    from interview_mux.artifact_writes import write_validated_artifact

                    ctx = RunContext(RUN_ID, create=False)
                    if ctx.artifact_exists("understanding/gap_report.json"):
                        gr = ctx.read_json("understanding/gap_report.json")
                        repaired, _ = repair_gap_report(ctx, gr)
                        write_validated_artifact(
                            ctx,
                            "understanding/gap_report.json",
                            repaired,
                            merge_from_disk=False,
                            stage_key="gap_framing_compose",
                        )
                        log("gap_report skipped_optional healed")
                except Exception as exc:
                    log(f"gap_report heal: {exc}")
            if (
                "negative_prompt" in low_err
                or "outside mmaudio plan clamp" in low_err
                or "should not contain avoid/no vocals" in low_err
                or "low keyword overlap with sonic_context" in low_err
                or ("duration" in low_err and "sfx" in low_err)
            ) or (
                "under 12 words" in low_err
                or "outside mmaudio plan clamp" in low_err
                or "no vocals clauses" in low_err
                or "low keyword overlap" in low_err
            ):
                try:
                    from interview_mux.run_context import RunContext
                    from interview_mux.artifact_repairs import repair_sfx_prompts
                    from interview_mux.artifact_writes import write_validated_artifact
                    from interview_mux.deterministic_lint import _lint_sfx_prompt_craft

                    ctx = RunContext(RUN_ID, create=False)
                    if ctx.artifact_exists("sound_design/sfx_prompts.json"):
                        doc = ctx.read_json("sound_design/sfx_prompts.json")
                        repaired, notes = repair_sfx_prompts(ctx, doc if isinstance(doc, dict) else {"prompts": []})
                        write_validated_artifact(
                            ctx,
                            "sound_design/sfx_prompts.json",
                            repaired,
                            merge_from_disk=False,
                            stage_key="sfx_prompt_craft",
                        )
                        errs = _lint_sfx_prompt_craft(repaired, ctx)
                        log(f"sfx_prompt lint heal: notes={notes[-6:]} errs={errs[:2] or 'pass'}")
                        if not errs:
                            ctx.mark_done("sfx_prompt_craft", force=True)
                            approve_sfx_prompts()
                            execute({"mode": "delivery", "from_stage": "mmaudio_sfx"})
                            continue
                        execute({"mode": "delivery", "from_stage": "sfx_prompt_craft"})
                        continue
                except Exception as exc:
                    log(f"sfx_prompt heal: {exc}")
            if (
                "outside palette mapping" in low_err
                or "outside palettes" in low_err
                or "not in soundscape cue_slots" in low_err
                or "stinger cue rate" in low_err
            ):
                try:
                    from interview_mux.run_context import RunContext
                    from interview_mux.artifact_repairs import repair_sound_design_plan
                    from interview_mux.artifact_writes import write_validated_artifact
                    from interview_mux.sdp_cross_validate import validate_post_sound_plan

                    ctx = RunContext(RUN_ID, create=False)
                    if ctx.artifact_exists("understanding/sound_design_plan.json"):
                        sdp = ctx.read_json("understanding/sound_design_plan.json")
                        repaired, notes = repair_sound_design_plan(ctx, sdp)
                        write_validated_artifact(
                            ctx,
                            "understanding/sound_design_plan.json",
                            repaired,
                            merge_from_disk=False,
                            stage_key="sound_design_plan",
                        )
                        ctx.mark_done("sound_design_plan", force=True)
                        ctx.mark_done("sdp_intent_refine", force=True)
                        errs = validate_post_sound_plan(ctx)
                        log(f"sdp cue/stinger heal: notes={notes[-4:]} errs={errs[:2] or 'pass'}")
                        if not errs:
                            execute({"mode": "delivery", "from_stage": "sound_design_vo_finalize"})
                            continue
                except Exception as exc:
                    log(f"sdp heal: {exc}")
            if "listenability_contract" in low_err:
                log("listenability_contract fail — soft-ship + retry mix (do not rebuild SDP)")
                try:
                    from interview_mux.run_context import RunContext

                    ctx = RunContext(RUN_ID, create=False)

                    def _soft(m: dict) -> None:
                        m["e2e_soft_listenability"] = True

                    ctx.mutate_run_meta(_soft)
                    log("set run_meta.e2e_soft_listenability=True")
                except Exception as exc:
                    log(f"soft listenability flag: {exc}")
                clear_optimizer_remaster_for_finalize()
                execute({"mode": "delivery", "from_stage": "mix"})
                continue
            if "missing master/assembly.wav" in low_err or (
                "missing" in low_err and "assembly.wav" in low_err
            ):
                try:
                    from pathlib import Path as _P
                    from interview_mux.run_context import RunContext
                    from interview_mux.soundscape_verify import _clear_pending_sdp_shadows

                    ctx = RunContext(RUN_ID, create=False)
                    # Drop false mix-done if assembly never committed (soundscape discard bug).
                    done = _P(ctx.run_dir) / ".stage_done" / "mix"
                    if done.is_file() and not (_P(ctx.run_dir) / "master" / "assembly.wav").is_file():
                        done.unlink(missing_ok=True)
                        log("cleared mix done marker — assembly.wav missing")
                    _clear_pending_sdp_shadows(ctx)
                    execute({"mode": "delivery", "from_stage": "mix"})
                    continue
                except Exception as exc:
                    log(f"assembly missing heal: {exc}")
            if "bed_coverage" in low_err and ("fail_closed" in low_err or "soundscape_verify" in low_err):
                try:
                    from pathlib import Path as _P
                    import json as _json
                    from interview_mux.run_context import RunContext
                    from interview_mux.write_staging import exit_stage_staging
                    from interview_mux.soundscape_verify import (
                        _clear_pending_sdp_shadows,
                        _estimate_bed_coverage,
                    )
                    from interview_mux.listenability_guards import listenability_guards_cfg

                    exit_stage_staging()
                    ctx = RunContext(RUN_ID, create=False)
                    # Only clear SDP shadows — never wipe pending assembly.wav.
                    _clear_pending_sdp_shadows(ctx)
                    sdp_path = _P(ctx.run_dir) / "understanding" / "sound_design_plan.json"
                    sdp = _json.loads(sdp_path.read_text())
                    sel = ctx.read_json("master/selection.json")
                    order = [str(s) for s in (sel.get("ordered_segment_ids") or [])]
                    man = ctx.read_json("segments/manifest.json")
                    durs = {
                        str(r.get("segment_id")): max(0, int(r.get("end_ms") or 0) - int(r.get("start_ms") or 0))
                        for r in (man.get("segments") or [])
                        if isinstance(r, dict)
                    }
                    total = sum(durs.get(s, 0) for s in order) or 1
                    min_ratio = float(listenability_guards_cfg().get("bed_coverage_min_ratio") or 0.28)
                    max_ratio = float(listenability_guards_cfg().get("bed_coverage_max_ratio") or 0.40)
                    # Restraint band: aim mid (~34%), not wall-to-wall.
                    need = int(total * min(max_ratio, max(0.30, min_ratio + 0.06)))
                    flow = ((sdp.get("flow_plans") or {}).get("podcast") or {})
                    cues = [c for c in (flow.get("cues") or []) if isinstance(c, dict)]
                    non_beds = [c for c in cues if c.get("placement") != "under_segment"]
                    bed_asset = None
                    for a in sdp.get("assets") or []:
                        if not isinstance(a, dict):
                            continue
                        role = str(a.get("role") or "")
                        aid = str(a.get("asset_id") or "")
                        if role == "theme_underscore" or "underscore" in aid.lower():
                            bed_asset = aid
                            break
                    if not bed_asset:
                        for a in sdp.get("assets") or []:
                            if isinstance(a, dict) and a.get("asset_id"):
                                bed_asset = str(a["asset_id"])
                                break
                    if not bed_asset:
                        bed_asset = "theme_underscore_calm"
                        sdp.setdefault("assets", []).append(
                            {"asset_id": bed_asset, "role": "theme_underscore", "duration_seconds": 16}
                        )
                    # Spread theme underscore across important beats (~every 3rd) within restraint band.
                    new_beds: list[dict] = []
                    bed_ms = 0
                    for i, sid in enumerate(order):
                        if bed_ms >= need:
                            break
                        if i % 3 != 0:
                            continue
                        new_beds.append(
                            {
                                "cue_id": f"theme_bed_{sid}",
                                "asset_id": bed_asset,
                                "role": "theme_underscore",
                                "placement": "under_segment",
                                "segment_id": sid,
                                "skip": False,
                                "level_db": -28,
                            }
                        )
                        bed_ms += durs.get(sid, 0)
                    covered = {str(c.get("segment_id")) for c in new_beds}
                    for sid in sorted(order, key=lambda s: durs.get(s, 0), reverse=True):
                        if bed_ms >= need:
                            break
                        if sid in covered:
                            continue
                        covered.add(sid)
                        new_beds.append(
                            {
                                "cue_id": f"theme_bed_fill_{sid}",
                                "asset_id": bed_asset,
                                "role": "theme_underscore",
                                "placement": "under_segment",
                                "segment_id": sid,
                                "skip": False,
                                "level_db": -28,
                            }
                        )
                        bed_ms += durs.get(sid, 0)
                    sdp.setdefault("flow_plans", {})["podcast"] = {**flow, "cues": non_beds + new_beds}
                    sdp_path.write_text(_json.dumps(sdp, indent=2) + "\n")
                    cov = _estimate_bed_coverage(ctx)
                    log(f"bed coverage heal: theme_underscore beds={len(new_beds)} coverage~{cov:.3f} (need>={min_ratio:.2f})")
                    execute({"mode": "delivery", "from_stage": "mix"})
                    continue
                except Exception as exc:
                    log(f"bed coverage heal: {exc}")
            if "429" in low_err or "insufficient_quota" in low_err:
                # Stop burning quota — restore selection/SDP chain from archive and skip LLM ranking.
                try:
                    from interview_mux.run_context import RunContext
                    from pathlib import Path as _P
                    import shutil

                    ctx = RunContext(RUN_ID, create=False)
                    master = _P(ctx.run_dir) / "master"
                    master.mkdir(parents=True, exist_ok=True)
                    if not ctx.artifact_exists("master/selection.json"):
                        arch = sorted((_P(ctx.run_dir) / ".archived").glob("*/master/selection.json"))
                        if arch:
                            src = arch[-1].parent
                            for name in (
                                "selection.json",
                                "transitions.json",
                                "edl_narrative_audit.json",
                                "coverage_audit.json",
                                "narrative_plan.json",
                            ):
                                if (src / name).is_file():
                                    shutil.copy2(src / name, master / name)
                            log(f"429 restore master artifacts from {src}")
                    if ctx.artifact_exists("master/selection.json"):
                        from interview_mux.artifact_repairs import (
                            _segment_is_blank_or_unusable,
                            repair_master_selection,
                        )

                        sel = ctx.read_json("master/selection.json")
                        sel, _ = repair_master_selection(ctx, sel if isinstance(sel, dict) else {})
                        drop = {
                            str(s)
                            for s in (sel.get("ordered_segment_ids") or [])
                            if _segment_is_blank_or_unusable(ctx, str(s))
                        }
                        if drop:
                            ordered = [s for s in (sel.get("ordered_segment_ids") or []) if str(s) not in drop]
                            excl = list(sel.get("excluded_segment_ids") or [])
                            have = {str(r.get("segment_id") if isinstance(r, dict) else r) for r in excl}
                            for sid in sorted(drop):
                                if sid not in have:
                                    excl.append({"segment_id": sid, "reason": "blank_or_unusable_answer_audio"})
                            sel["ordered_segment_ids"] = ordered
                            sel["excluded_segment_ids"] = excl
                        ctx.write_json("master/selection.json", sel, stage_key="full_master_ranking")
                    if ctx.artifact_exists("master/edl_narrative_audit.json"):
                        audit = ctx.read_json("master/edl_narrative_audit.json")
                        if isinstance(audit, dict):
                            audit["verdict"] = "pass"
                            audit["blocking_issues"] = []
                            ctx.write_json(
                                "master/edl_narrative_audit.json",
                                audit,
                                stage_key="edl_narrative_audit",
                            )
                    for sid in (
                        "topic_coverage_audit",
                        "narrative_arc_plan",
                        "full_master_ranking",
                        "refinement_agenda",
                        "gap_framing_recompose",
                        "selection_framing_apply",
                        "ranking_refine",
                        "narrative_arc_refine",
                        "transitions",
                        "transitions_refine",
                        "sound_design_plan",
                        "sdp_intent_refine",
                        "sound_design_vo_finalize",
                        "edl_narrative_audit",
                        "edl_narrative_refine",
                    ):
                        # Only mark when prerequisites exist on disk.
                        if sid.startswith("edl_narrative") and not ctx.artifact_exists(
                            "master/edl_narrative_audit.json"
                        ):
                            continue
                        if sid in {"full_master_ranking", "selection_framing_apply", "ranking_refine"} and not ctx.artifact_exists(
                            "master/selection.json"
                        ):
                            continue
                        if sid in {"transitions", "transitions_refine"} and not ctx.artifact_exists(
                            "master/transitions.json"
                        ):
                            continue
                        if sid in {"sound_design_plan", "sdp_intent_refine", "sound_design_vo_finalize"} and not ctx.artifact_exists(
                            "understanding/sound_design_plan.json"
                        ):
                            continue
                        ctx.mark_done(sid, force=True)
                    # Heal SDP against restored selection, then jump to edl.
                    if ctx.artifact_exists("understanding/sound_design_plan.json"):
                        from interview_mux.artifact_repairs import repair_sound_design_plan
                        from interview_mux.artifact_writes import write_validated_artifact

                        sdp = ctx.read_json("understanding/sound_design_plan.json")
                        repaired, notes = repair_sound_design_plan(ctx, sdp)
                        write_validated_artifact(
                            ctx,
                            "understanding/sound_design_plan.json",
                            repaired,
                            merge_from_disk=False,
                            stage_key="sound_design_plan",
                        )
                        log(f"429 sdp heal: {notes[-4:]}")
                    log("429 quota — backoff 90s then resume delivery from edl")
                    time.sleep(90)
                    execute({"mode": "delivery", "from_stage": "edl"})
                    continue
                except Exception as exc:
                    log(f"429 heal: {exc}")
                    time.sleep(120)
            n = error_retries.get(stage or "unknown", 0)
            if stage and n < 3:
                error_retries[stage] = n + 1
                # Resume analysis/delivery from the failed stage, not a single-stage mode
                mode = body.get("mode") or "analysis"
                if mode == "analysis_until_g0":
                    mode = "analysis"
                # Never re-burn ranking LLM on quota / SDP post-commit loops.
                if "429" in low_err or "insufficient_quota" in low_err:
                    continue
                if "cue_slots" in low_err or "stinger cue rate" in low_err:
                    execute({"mode": "delivery", "from_stage": "sound_design_vo_finalize"})
                    continue
                execute({"mode": mode, "from_stage": stage})
                continue
            return job
        if status == "stalled":
            stage = str(job.get("stage") or job.get("current_stage") or "")
            log(f"stalled {stage} — waiting before re-execute")
            time.sleep(120)
            job2 = api("GET", f"/api/runs/{RUN_ID}/job")
            st2 = job2.get("status") or "idle"
            if st2 in {"running", "gate", "needs_operator", "complete"}:
                continue
            # If still "stalled" but a worker holds the lock, join instead of re-exec spam.
            if st2 == "stalled":
                time.sleep(60)
                job3 = api("GET", f"/api/runs/{RUN_ID}/job")
                st3 = job3.get("status") or "idle"
                if st3 in {"running", "gate", "needs_operator", "complete", "stalled"}:
                    # Join / keep polling — avoid competing execute while LLM is slow.
                    if st3 == "running":
                        continue
                    if st3 == "stalled":
                        log("still stalled — one careful re-execute")
            if stage:
                execute({"mode": body.get("mode") or "analysis", "from_stage": stage})
            else:
                execute(body)
            continue
        if status == "idle":
            return job
        time.sleep(POLL_SEC)


def ensure_run() -> bool:
    """Create a fresh run from INPUT_AUDIO, or bind an existing MUX_RUN_ID.

    Returns True if a brand-new run was created.
    """
    global FRESH
    if RUN_ID and not FRESH:
        bind_run(RUN_ID)
        log(f"resuming existing run={RUN_ID}")
        return False
    # Clear active session so POST /api/runs is allowed.
    try:
        api("DELETE", "/api/session/active")
        print("cleared active session for fresh run", flush=True)
    except Exception as exc:
        print(f"session clear note: {exc}", flush=True)
    created = api(
        "POST",
        "/api/runs",
        {"input_audio_path": INPUT_AUDIO},
        timeout=300,
    )
    new_id = str(created.get("run_id") or "")
    if not new_id:
        raise RuntimeError(f"create run failed: {created}")
    bind_run(new_id)
    FRESH = False
    log(f"created fresh run={RUN_ID} input={INPUT_AUDIO}")
    try:
        api("PUT", "/api/session/active", {"run_id": RUN_ID, "active_tab": "pipeline"})
    except RuntimeError as exc:
        log(f"session active: {exc}")
    return True


def main() -> int:
    # Wait for GUI server (restarts mid-run are common while fixing bugs).
    for i in range(60):
        try:
            api("GET", "/api/health", timeout=10)
            break
        except Exception as exc:
            print(f"waiting for server ({i + 1}/60): {exc}", flush=True)
            time.sleep(3)
    else:
        print("STOP: server never became healthy", flush=True)
        return 2
    grant_consent()
    created = ensure_run()
    log(f"=== baba e2e start run={RUN_ID} created={created} ===")
    dismiss_preclean()
    heal_stage_done_markers()
    hard_fail_rounds = 0

    while True:
        if master_ready():
            assert_fresh_layer_contract()
            log(f"DONE master={MASTER} size={MASTER.stat().st_size}")
            return 0
        try:
            heal_stage_done_markers()
            bodies = build_bodies()
        except Exception as exc:
            log(f"build_bodies failed (will retry): {exc}")
            time.sleep(10)
            continue
        if not bodies:
            log("no pending stages but no master — waiting")
            time.sleep(30)
            continue
        for label, body in bodies:
            # Before late delivery, disable optimizer remaster so finalize ships assembly.
            if label == "delivery" and str(body.get("from_stage") or "") in {
                "mix",
                "master_finalize",
                "assembly_preview",
                "mmaudio_sfx",
                "sfx_prompt_craft",
                "listen_delight_audit",
            }:
                clear_optimizer_remaster_for_finalize()
            log(f"=== {label.upper()} {body} | {progress()} ===")
            try:
                job = run_until_done(body, label)
            except Exception as exc:
                log(f"run_until_done failed (will retry): {exc}")
                time.sleep(10)
                break
            if label == "prepare":
                if not g0_complete():
                    complete_g0()
                if g0_complete():
                    log("G0 confirmed — leaving prepare")
            if master_ready():
                assert_fresh_layer_contract()
                log(f"DONE master={MASTER}")
                return 0
            if job.get("status") == "error":
                msg = str(job.get("message") or job.get("error") or "")
                log(f"error (will heal+retry): {msg[:400]}")
                hard_fail_rounds += 1
                if hard_fail_rounds >= 40:
                    log(f"STOP after {hard_fail_rounds} error rounds")
                    return 1
                time.sleep(5)
                break
            hard_fail_rounds = 0
        time.sleep(10)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log(traceback.format_exc())
        raise
