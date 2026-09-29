"""Operator gates for gap framing path (G-Framing, G-Delivery, G-VoiceRef)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.config import merged_config
from interview_mux.conversation_context import role_is_frame
from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
from interview_mux.run_context import RunContext
from interview_mux.source_topology import (
    load_flow_adaptation,
    pickup_eligible_speaker_id,
    pickup_speaker_confirmed,
)

GapVoDelivery = Literal["chatterbox", "record"]


def gap_fill_cfg_block(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    raw = analysis.get("gap_fill") or {}
    defaults = {
        "enabled": True,
        "default_framing_enabled": True,
        "require_explicit_opt_in": True,
        "auto_accept_defaults": True,
        "succinct_master_default": True,
        "auto_skip_when_ineligible": False,
        "frame_confidence_min": 0.65,
        "hide_gui_stages_when_skipped": True,
    }
    if isinstance(raw, dict):
        return {**defaults, **raw}
    return defaults


def auto_accept_gap_gate_defaults_enabled(cfg: dict[str, Any] | None = None) -> bool:
    """True when env/config may apply gap gate product defaults without a human.

    Shipped default: ``analysis.gap_fill.auto_accept_defaults=true`` (Q4B).
    Env ``INTERVIEW_MUX_AUTO_ACCEPT_GATES=1`` still forces on.
    True-monologue / topology skip still skips gap-fill; ambiguous clone host
    still blocks voice-ref auto-approve.
    """
    env = os.environ.get("INTERVIEW_MUX_AUTO_ACCEPT_GATES", "").strip().lower()
    if env in {"1", "true", "yes", "on"}:
        return True
    return bool(gap_fill_cfg_block(cfg).get("auto_accept_defaults", True))


def _run_meta(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists("run_meta.json"):
        doc = ctx.read_json("run_meta.json")
        if isinstance(doc, dict):
            return doc
    return {}


def gap_framing_enabled(ctx: RunContext) -> bool:
    if gap_fill_was_skipped(ctx):
        return False
    meta = _run_meta(ctx)
    if "gap_framing_enabled" in meta:
        return bool(meta.get("gap_framing_enabled"))
    adapt = load_flow_adaptation(ctx) or {}
    overrides = adapt.get("operator_overrides") or {}
    if "gap_framing_enabled" in overrides:
        return bool(overrides.get("gap_framing_enabled"))
    return bool(gap_fill_cfg_block().get("default_framing_enabled", True))


def recommended_gap_framing_enabled() -> bool:
    """Product default offered at G-Framing (operator must still confirm unless auto-accept)."""
    return bool(gap_fill_cfg_block().get("default_framing_enabled", True))


def set_gap_framing_enabled(ctx: RunContext, enabled: bool) -> None:
    from interview_mux.gap_fill_eligibility import clear_gap_fill_skip
    from interview_mux.stages.gaps import ensure_gap_fill_skipped

    def patch(meta: dict[str, Any]) -> None:
        meta["gap_framing_enabled"] = enabled
        if enabled:
            meta["gap_fill_mode"] = "active"
            meta.pop("gap_fill_skip_reason", None)
        else:
            meta["gap_fill_mode"] = "skipped"

    ctx.mutate_run_meta(patch)
    adapt = load_flow_adaptation(ctx) or {}
    overrides = dict(adapt.get("operator_overrides") or {})
    overrides["gap_framing_enabled"] = enabled
    if not enabled:
        overrides["gap_fill_skipped"] = True
    else:
        overrides.pop("gap_fill_skipped", None)
    adapt["operator_overrides"] = overrides
    ctx.write_json(
        "understanding/flow_adaptation.json",
        adapt,
        skip_handoff=True,
        stage_key="missing_framing",
    )
    try:
        from interview_mux.pipeline_mode import persist_pipeline_mode

        if enabled:
            persist_pipeline_mode(
                ctx,
                "framing_full",
                decided_by="operator_g_framing",
                reason_codes=["gap_framing_yes"],
            )
        else:
            persist_pipeline_mode(
                ctx,
                "native_only",
                decided_by="operator_g_framing",
                reason_codes=["gap_framing_no"],
            )
    except Exception:
        pass
    if enabled:
        clear_gap_fill_skip(ctx, reason="operator_enabled_gap_framing")
    else:
        ensure_gap_fill_skipped(
            ctx,
            reason="gap_framing_disabled_by_operator",
            signals={"skip_signal": "gap_framing_no"},
        )


def resolve_gap_vo_delivery(ctx: RunContext) -> GapVoDelivery:
    meta = _run_meta(ctx)
    raw = str(meta.get("gap_vo_delivery") or "").strip().lower()
    if raw in {"chatterbox", "record"}:
        return raw  # type: ignore[return-value]
    from interview_mux.gap_framing import gap_vo_cfg

    default = str(gap_vo_cfg().get("default_delivery", "chatterbox")).lower()
    return "chatterbox" if default == "chatterbox" else "record"


def rewrite_full_auto_record_lines_to_synth(
    ctx: RunContext,
    *,
    stage_key: str | None = None,
) -> list[str]:
    """Full-auto owns formerly record-required gap lines via synthesize (VS-B3 / Q3B).

    Persists ``delivery: synthesize`` on open record lines so G1 does not stall
    for a human take and ``vo_synthesize`` / ensure_g1 can close the WAVs.
    Requires an approved voice reference (clone path). No-op outside Full-auto;
    partial-auto keeps HV-5 record hard_block.

    ``stage_key`` defaults to the active stage (caller), then ``vo_synthesize``.
    Never hardcode a foreign writer when invoked from ``vo_line_adjudicate``.
    """
    from interview_mux.automation_run import is_full_auto_run

    try:
        from interview_mux.write_staging import active_stage_id

        writer = str(stage_key or active_stage_id() or "").strip() or "vo_synthesize"
    except Exception:
        writer = str(stage_key or "").strip() or "vo_synthesize"

    meta = _run_meta(ctx)
    if not is_full_auto_run(meta):
        return []
    if gap_fill_was_skipped(ctx):
        return []
    ok, reason = vo_path_ready(ctx, for_synthesize=False)
    if not ok:
        ctx.log(
            f"Full-auto record→synth skipped — vo_path not ready ({reason})",
            level="info",
            stage=writer,
        )
        return []
    if resolve_gap_vo_delivery(ctx) != "chatterbox":
        ctx.log(
            "Full-auto record→synth skipped — delivery is not chatterbox",
            level="info",
            stage=writer,
        )
        return []
    if not voice_reference_approved(ctx):
        ctx.log(
            "Full-auto record→synth skipped — voice reference not approved yet",
            level="info",
            stage=writer,
        )
        return []
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    try:
        gap = ctx.read_json("understanding/gap_report.json")
    except Exception:
        return []
    if not isinstance(gap, dict):
        return []
    lines = gap.get("interviewer_lines")
    if not isinstance(lines, list):
        return []

    rewritten: list[str] = []
    changed = False
    for row in lines:
        if not isinstance(row, dict):
            continue
        if row.get("skipped_optional") or row.get("air_script_omit"):
            continue
        delivery = str(row.get("delivery") or "").strip().lower()
        if delivery != "record":
            continue
        lid = str(row.get("line_id") or "").strip()
        if not lid:
            continue
        row["delivery"] = "synthesize"
        row["full_auto_record_rewritten"] = True
        rewritten.append(lid)
        changed = True
    if not changed:
        return []
    try:
        ctx.write_json(
            "understanding/gap_report.json",
            gap,
            stage_key=writer,
        )
    except Exception as exc:
        ctx.log(
            f"full-auto record→synth rewrite persist failed: {exc}",
            level="warning",
            stage=writer,
        )
        return []
    try:
        from interview_mux.delivery_invariants import sync_vo_line_owners

        sync_vo_line_owners(ctx)
    except Exception:
        pass
    ctx.log(
        "Full-auto rewrote record-required VO lines to synthesize: "
        + ", ".join(rewritten[:12]),
        level="warning",
        stage=writer,
        detail={"rewritten_line_ids": rewritten, "stage_key": writer},
    )
    return rewritten


def set_gap_vo_delivery(ctx: RunContext, delivery: str) -> None:
    d = str(delivery or "").strip().lower()
    if d not in {"chatterbox", "record"}:
        raise ValueError("delivery must be chatterbox or record")

    def patch(meta: dict[str, Any]) -> None:
        meta["gap_vo_delivery"] = d

    ctx.mutate_run_meta(patch)


def voice_reference_approved(ctx: RunContext) -> bool:
    meta = _run_meta(ctx)
    if meta.get("voice_reference_approved_at"):
        return True
    speaker_id = pickup_eligible_speaker_id(ctx)
    if not speaker_id:
        return False
    rel = f"understanding/voice_reference/{speaker_id}.json"
    if not ctx.artifact_exists(rel):
        return False
    doc = ctx.read_json(rel)
    return isinstance(doc, dict) and bool(doc.get("approved"))


def check_gap_framing_decision_pending(ctx: RunContext) -> bool:
    """True when operator has not chosen yes/no for gap framing."""
    if gap_fill_was_skipped(ctx):
        return False
    meta = _run_meta(ctx)
    if "gap_framing_enabled" in meta:
        return False
    adapt = load_flow_adaptation(ctx) or {}
    overrides = adapt.get("operator_overrides") or {}
    if "gap_framing_enabled" in overrides:
        return False
    if not ctx.is_done("source_topology_build"):
        return False
    from interview_mux.pipeline import ANALYSIS_ORDER

    idx = ANALYSIS_ORDER.index("missing_framing")
    for sid in ANALYSIS_ORDER[:idx]:
        if not ctx.is_done(sid):
            return False
    return True


def check_gap_delivery_pending(ctx: RunContext) -> bool:
    if not gap_framing_enabled(ctx):
        return False
    if not voice_reference_approved(ctx):
        return False
    meta = _run_meta(ctx)
    return "gap_vo_delivery" not in meta


def check_voice_reference_pending(ctx: RunContext) -> bool:
    if not gap_framing_enabled(ctx):
        return False
    # No pickup-eligible speaker determined yet (topology/adaptation not built) — nothing to
    # approve, mirrors the prerequisite guard in check_pickup_speaker_pending.
    if pickup_eligible_speaker_id(ctx) is None:
        return False
    # Approved voice clears HG-4 heal remap even if pickup-speaker confirm races.
    # Without this, premature_complete on topic_coverage_audit remaps to already-done
    # missing_framing → spine-freeze "Finished: Gap evaluation" sticky ×N.
    if voice_reference_approved(ctx):
        return False
    if not pickup_speaker_confirmed(ctx):
        return True
    return not voice_reference_approved(ctx)


def approved_voice_reference_usable(ctx: RunContext) -> bool:
    """True when an approved voice-ref points at an on-disk WAV meeting min duration."""
    if not voice_reference_approved(ctx):
        return False
    speaker_id = pickup_eligible_speaker_id(ctx)
    if not speaker_id:
        return False
    rel = f"understanding/voice_reference/{speaker_id}.json"
    wav_rel = f"understanding/speaker_samples/{speaker_id}.wav"
    if ctx.artifact_exists(rel):
        try:
            doc = ctx.read_json(rel)
            if isinstance(doc, dict) and doc.get("wav"):
                wav_rel = str(doc["wav"])
        except Exception:
            pass
    try:
        path = ctx.read_path(*wav_rel.split("/"))
    except Exception:
        return False
    if not path.is_file() or path.stat().st_size < 64:
        return False
    try:
        from interview_mux.voice_reference import _reference_duration_sec, voice_reference_cfg

        min_sec = float(voice_reference_cfg().get("min_reference_sec", 3.0))
        return _reference_duration_sec(path) + 1e-9 >= min_sec
    except Exception:
        return path.is_file()


def _intended_synthesize_line_count(ctx: RunContext) -> int:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return 0
    try:
        gap = ctx.read_json("understanding/gap_report.json")
    except Exception:
        return 0
    if not isinstance(gap, dict):
        return 0
    n = 0
    for row in gap.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        if row.get("skipped_optional") or row.get("air_script_omit"):
            continue
        delivery = str(row.get("delivery") or "").strip().lower()
        if delivery in {"synthesize", "chatterbox", "voice_clone"}:
            n += 1
    return n


def vo_path_ready(
    ctx: RunContext,
    *,
    for_synthesize: bool = False,
) -> tuple[bool, str]:
    """SSOT: may compose clone-implying scripts / offer G1 synth / run Chatterbox.

    Returns ``(ok, reason_code)``. ``reason_code`` is empty when ok.
    Gap framing disabled or skipped → ready (no VO path to gate).
    """
    if gap_fill_was_skipped(ctx) or not gap_framing_enabled(ctx):
        return True, ""
    if check_gap_framing_decision_pending(ctx):
        return False, "gap_framing_pending"
    # Honest pickup: require confirm stamp; do not treat missing_framing done as enough.
    if not pickup_speaker_confirmed(ctx):
        return False, "pickup_speaker_pending"
    if not voice_reference_approved(ctx):
        return False, "voice_reference_pending"
    meta = _run_meta(ctx)
    if "gap_vo_delivery" not in meta:
        return False, "gap_delivery_pending"
    from interview_mux.mastering_hardening_config import gate_blocks

    if gate_blocks("voice_clone") and check_clone_consent_pending(ctx):
        return False, "clone_consent_pending"
    if resolve_gap_vo_delivery(ctx) == "chatterbox" and not approved_voice_reference_usable(ctx):
        # Approved but the WAV is gone: rebuild once rather than dead-ending. The
        # approval stamp means no gate will reopen to fix this by itself.
        if not repair_unusable_voice_reference(ctx):
            return False, "voice_reference_unusable"
    if for_synthesize and resolve_gap_vo_delivery(ctx) == "chatterbox":
        if _intended_synthesize_line_count(ctx) < 1:
            try:
                from interview_mux.hosted_vo_authority import identify_hosted_vo_floor

                ident = identify_hosted_vo_floor(
                    ctx, stage_id="vo_synthesize", persist=True
                )
                suffix = (
                    f"{ident.status}:{ident.prose} resume={ident.resume_producer}"
                )
                return False, f"no_synthesize_lines:{suffix}"
            except Exception:
                pass
            # Rewrite path may arm lines; still refuse hollow synth-all with no targets.
            return False, "no_synthesize_lines"
    return True, ""


def vo_ladder_complete(
    ctx: RunContext,
    *,
    for_synthesize: bool = False,
) -> tuple[bool, str]:
    """DP-VO1 A+: synth-critical ladder beyond gate stamps.

    - Always includes ``vo_path_ready`` (pickup / voice-ref / delivery / consent).
    - When ``for_synthesize``: also requires seed-complete ``vo_line_adjudicate``
      (when gap framing is on) and Chatterbox G8 ``vo_synthesize_stability_block``
      clear (read-only probe — no Full-auto rewrite side effect).

    Framing / G1 ``automation_pending`` is **not** ladder-complete — drivers may
    look green while this returns false.
    """
    ok, reason = vo_path_ready(ctx, for_synthesize=for_synthesize)
    if not ok:
        return False, reason
    if not for_synthesize:
        return True, ""
    if gap_fill_was_skipped(ctx) or not gap_framing_enabled(ctx):
        return True, ""
    # Never treat bare ``is_done`` as adjudicate seal (hollow marker footgun).
    try:
        from interview_mux.delivery_guardrails import seed_stage_complete

        if not seed_stage_complete(ctx, "vo_line_adjudicate"):
            return False, "vo_line_adjudicate_incomplete"
    except Exception:
        return False, "vo_line_adjudicate_incomplete"
    if resolve_gap_vo_delivery(ctx) == "chatterbox":
        try:
            from interview_mux.delivery_guardrails import vo_synthesize_stability_block

            block = vo_synthesize_stability_block(ctx, allow_rewrite=False)
            if block:
                return False, f"vo_synth_stability:{block}"
        except Exception:
            return False, "vo_synth_stability:probe_error"
    return True, ""


def vo_synth_mint_allowed(
    ctx: RunContext,
    *,
    for_synthesize: bool = False,
) -> tuple[bool, str]:
    """Whether Chatterbox/S2S may mint a WAV for gap framing.

    Partial: full ``vo_ladder_complete`` (no early nested mint past open ladder).
    Full-auto / interactive: ``vo_path_ready`` only so nested EDL/transition mint
    can still proceed after gates stamp (NESTED-SYNTH Full-auto path).
    """
    try:
        from interview_mux.automation_run import is_partially_accelerated_run

        if is_partially_accelerated_run(_run_meta(ctx)):
            return vo_ladder_complete(ctx, for_synthesize=True)
    except Exception:
        # Fail closed toward Partial honesty if mode probe fails.
        return vo_ladder_complete(ctx, for_synthesize=True)
    return vo_path_ready(ctx, for_synthesize=for_synthesize)


def synth_entry_may_auto_accept(ctx: RunContext) -> bool:
    """A+ Partial vs Full-auto matrix for ``require_vo_path_ready`` on synth entry.

    Partial: never stamp gap gates from ``vo_synthesize`` / synth-all (framing
    auto-accept remains via ``maybe_auto_accept_gap_gate_defaults`` elsewhere).
    Full-auto: may auto-accept then proceed.
    Interactive: honor caller (no Partial special-case).
    """
    try:
        from interview_mux.automation_run import (
            is_full_auto_run,
            is_partially_accelerated_run,
        )

        meta = _run_meta(ctx)
        if is_partially_accelerated_run(meta):
            return False
        if is_full_auto_run(meta):
            return True
    except Exception:
        pass
    return True


_VO_PATH_EXIT: dict[str, str] = {
    "gap_framing_pending": (
        "Gap framing gate: choose whether to add interviewer framing audio in the GUI"
    ),
    "pickup_speaker_pending": (
        "Gap pickup speaker gate: confirm who will record gap-fill lines in the GUI"
    ),
    "voice_reference_pending": (
        "Voice reference gate: approve interviewer voice sample before gap framing LLM stages."
    ),
    "gap_delivery_pending": (
        "Gap delivery gate: choose Chatterbox clone or record-as-interviewer before gap framing."
    ),
    "clone_consent_pending": (
        "Voice clone gate: record clone consent and usage scope in the GUI before "
        "synthesizing pickup VO — docs/cross-cutting/mastering-voice-clone-policy.md"
    ),
    "voice_reference_unusable": (
        "Voice reference gate: approved reference WAV missing or too short for clone."
    ),
    "no_synthesize_lines": (
        "Gap VO gate: no synthesize lines armed — compose or rewrite record→synth first."
    ),
    "vo_line_adjudicate_incomplete": (
        "VO ladder: vo_line_adjudicate not seed-complete — finish adjudicate before synth."
    ),
}


def framing_requires_nested_synth_gate(ctx: RunContext) -> bool:
    """True when resync/nested mint must consult ``nested_synth_may_mint``.

    DP-NESTED-SYNTH residuals:
    - Gate whenever gap framing is on (not only when delivery already ∈ chatterbox).
    - If framing probe throws under Partial → assume gate required (fail closed).
    """
    try:
        if gap_fill_was_skipped(ctx):
            return False
        return bool(gap_framing_enabled(ctx))
    except Exception:
        try:
            from interview_mux.automation_run import is_partially_accelerated_run

            if is_partially_accelerated_run(_run_meta(ctx)):
                return True
        except Exception:
            return True
        return False


def nested_synth_may_mint(
    ctx: RunContext,
    *,
    for_synthesize: bool = False,
) -> tuple[bool, str]:
    """Whether nested EDL/transition Chatterbox may mint WAVs.

    Partial (and manual): never auto-accept gates; if ladder not ready → skip mint
    (caller continues without SystemExit). Full-auto may auto-accept then mint.

    Returns ``(ok, note)``. ``note`` is empty when ok; otherwise a skip token such as
    ``nested_synth_skipped:vo_path_not_ready:<reason_code>``.
    """
    try:
        if gap_fill_was_skipped(ctx) or not gap_framing_enabled(ctx):
            return True, ""
    except Exception:
        # Framing probe failed — fail closed for all modes (footgun #4).
        return False, "nested_synth_skipped:vo_path_not_ready:framing_probe_error"

    delivery = resolve_gap_vo_delivery(ctx)
    # Nested Chatterbox must not mint under explicit record delivery.
    if delivery == "record":
        return False, "nested_synth_skipped:vo_path_not_ready:record_delivery"

    auto_accept = False
    try:
        from interview_mux.automation_run import is_full_auto_run, is_partially_accelerated_run

        meta = _run_meta(ctx)
        if is_partially_accelerated_run(meta):
            auto_accept = False
        elif is_full_auto_run(meta):
            auto_accept = True
    except Exception:
        auto_accept = False

    if auto_accept:
        try:
            maybe_auto_accept_gap_gate_defaults(ctx)
        except Exception:
            pass

    try:
        ok, reason = vo_synth_mint_allowed(ctx, for_synthesize=for_synthesize)
    except Exception:
        # Fail closed: Partial/manual must not mint when the ladder probe crashes.
        return False, "nested_synth_skipped:vo_path_not_ready:probe_error"
    if ok:
        return True, ""
    code = reason or "vo_path_not_ready"
    return False, f"nested_synth_skipped:vo_path_not_ready:{code}"


def repair_unusable_voice_reference(ctx: RunContext) -> bool:
    """Rebuild an approved voice reference whose WAV is gone. True when usable after.

    ``voice_reference_unusable`` was a dead end: the approval stamp keeps
    ``check_voice_reference_pending`` False, so no gate reopens and no playbook
    covers it, and the run can only hard-stop. The inputs the approval was built
    from (the candidates manifest and its clips) are separate artifacts that
    normally survive, so the reference can be rebuilt without the operator and
    without the model.

    Attempted once per run; a second failure is a real stop, not a retry loop.
    """
    if approved_voice_reference_usable(ctx):
        return True
    speaker_id = pickup_eligible_speaker_id(ctx)
    if not speaker_id:
        return False
    # The attempt is stamped in run_meta rather than a sidecar artifact: this can
    # run inside a staged stage, and a sidecar under understanding/ would be a
    # new unowned path, i.e. the very failure being repaired. run_meta is
    # operational and already carries the gate stamps.
    meta = _run_meta(ctx)
    if meta.get("voice_reference_repair_attempted_at"):
        return False

    def _stamp(doc: dict[str, Any]) -> None:
        doc["voice_reference_repair_attempted_at"] = datetime.now(timezone.utc).isoformat()
        doc["voice_reference_repair_speaker_id"] = speaker_id

    try:
        ctx.mutate_run_meta(_stamp)
    except Exception:
        return False
    try:
        from interview_mux.voice_reference import approve_voice_reference

        approve_voice_reference(ctx, speaker_id)
    except Exception as exc:
        ctx.log(
            f"Voice reference repair failed for {speaker_id}: {exc}",
            level="warn",
            action_id="auto.voice_reference.repair",
            detail={"kind": "gate", "event": "voice_reference_repair_failed"},
        )
        return False
    ok = approved_voice_reference_usable(ctx)
    ctx.log(
        f"Voice reference rebuilt for {speaker_id} (approved sample was missing)",
        level="info" if ok else "warn",
        action_id="auto.voice_reference.repair",
        detail={"kind": "gate", "event": "voice_reference_repaired", "usable": ok},
    )
    return ok


def require_vo_path_ready(
    ctx: RunContext,
    *,
    for_synthesize: bool = False,
    auto_accept: bool = True,
) -> None:
    """Refuse loudly when the VO ladder is not ready (SystemExit).

    When ``for_synthesize``: uses ``vo_ladder_complete`` (adjudicate + G8).
    Otherwise: ``vo_path_ready`` only (framing/compose gates).

    A+ auto_accept: on synth entry, Partial never stamps gates even if
    ``auto_accept=True``; Full-auto may. Framing path honors ``auto_accept``.
    """
    do_accept = bool(auto_accept)
    if for_synthesize and do_accept:
        do_accept = synth_entry_may_auto_accept(ctx)
    if do_accept:
        try:
            maybe_auto_accept_gap_gate_defaults(ctx)
        except Exception:
            pass
    if for_synthesize:
        ok, reason = vo_ladder_complete(ctx, for_synthesize=True)
    else:
        ok, reason = vo_path_ready(ctx, for_synthesize=False)
    if ok:
        return
    if reason.startswith("vo_synth_stability:"):
        token = reason.split(":", 1)[-1]
        prose = (
            f"VO ladder: Chatterbox stability blocked ({token}) — "
            "finish layup/transitions before synth."
        )
    elif reason.startswith("no_synthesize_lines"):
        base = _VO_PATH_EXIT.get(
            "no_synthesize_lines",
            "Gap VO gate: no synthesize lines armed — compose or rewrite record→synth first.",
        )
        if reason == "no_synthesize_lines":
            try:
                from interview_mux.hosted_vo_authority import identify_hosted_vo_floor

                ident = identify_hosted_vo_floor(
                    ctx, stage_id="vo_synthesize", persist=True
                )
                prose = f"{base} — {ident.prose} resume={ident.resume_producer}"
            except Exception:
                prose = base
        else:
            prose = f"{base} ({reason.split(':', 1)[-1]})"
    else:
        prose = _VO_PATH_EXIT.get(reason, f"Gap VO path not ready ({reason})")
    if reason == "pickup_speaker_pending":
        raise SystemExit(
            f"{prose} → {ctx.path('understanding/flow_adaptation.json')}"
        )
    if reason == "gap_framing_pending":
        raise SystemExit(f"{prose} → {ctx.path('run_meta.json')}")
    raise SystemExit(prose)


def require_gap_framing_decision_clear(ctx: RunContext) -> None:
    if check_gap_framing_decision_pending(ctx):
        # Full-auto / Homunculus: stamp the decision before SystemExit so the
        # driver is not stuck behind sticky needs_operator while the gate is open.
        try:
            if maybe_auto_accept_gap_gate_defaults(ctx) and not check_gap_framing_decision_pending(
                ctx
            ):
                return
        except Exception:
            pass
        raise SystemExit(
            "Gap framing gate: choose whether to add interviewer framing audio in the GUI "
            f"→ {ctx.path('run_meta.json')}"
        )


def require_gap_path_clear(ctx: RunContext) -> None:
    """Compose / framing path clear — delegates to ``vo_path_ready`` SSOT."""
    if not gap_framing_enabled(ctx):
        return
    require_vo_path_ready(ctx, for_synthesize=False, auto_accept=True)


def mark_voice_reference_approved(ctx: RunContext, speaker_id: str) -> None:
    from interview_mux.conversation_context import load_conversation_context

    conv = load_conversation_context(ctx)
    sp = conv.speaker_by_id.get(speaker_id) or {}
    role = str(sp.get("role") or "")
    if not role_is_frame(role):
        raise ValueError(f"Speaker {speaker_id} is not a frame role ({role})")
    rel = f"understanding/voice_reference/{speaker_id}.json"
    doc = ctx.read_json(rel) if ctx.artifact_exists(rel) else {"speaker_id": speaker_id}
    if not isinstance(doc, dict):
        doc = {"speaker_id": speaker_id}
    doc["approved"] = True
    doc["approved_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json(rel, doc)

    def patch(meta: dict[str, Any]) -> None:
        meta["voice_reference_approved_at"] = doc["approved_at"]

    ctx.mutate_run_meta(patch)


def clone_consent_required(ctx: RunContext) -> bool:
    """Chatterbox delivery synthesizes the pickup voice, so it needs clone consent."""
    if not gap_framing_enabled(ctx):
        return False
    return resolve_gap_vo_delivery(ctx) == "chatterbox"


def check_clone_consent_pending(ctx: RunContext) -> bool:
    from interview_mux.mastering_voice_clone import consent_active, load_consent

    if not clone_consent_required(ctx):
        return False
    if not voice_reference_approved(ctx):
        return False
    return not consent_active(load_consent(ctx))


def require_clone_consent_clear(ctx: RunContext) -> None:
    from interview_mux.mastering_hardening_config import gate_blocks

    if not gate_blocks("voice_clone"):
        return
    if check_clone_consent_pending(ctx):
        raise SystemExit(
            "Voice clone gate: record clone consent and usage scope in the GUI before "
            "synthesizing pickup VO — docs/cross-cutting/mastering-voice-clone-policy.md"
        )


def maybe_auto_accept_gap_gate_defaults(ctx: RunContext) -> bool:
    """Apply product defaults for unattended / E2E / Homunculus auto-resolve Yes.

    B1: Full-auto arms the same path as homunculus ``auto_resolve`` when the
    recommended framing action is ``auto_resolve`` (independent of
    ``has_homunculus_features`` and of ``auto_accept_defaults`` / env).
    """
    homunculus_auto = False
    full_auto_arms = False
    try:
        from interview_mux.homunculus.gates import recommended_framing_action
        from interview_mux.homunculus.runtime import has_homunculus_features

        rec = recommended_framing_action(ctx)
        homunculus_auto = has_homunculus_features(ctx) and rec == "auto_resolve"
        if rec == "auto_resolve":
            try:
                from interview_mux.automation_run import is_full_auto_run

                meta = (
                    ctx.read_json("run_meta.json")
                    if ctx.artifact_exists("run_meta.json")
                    else {}
                )
                full_auto_arms = is_full_auto_run(
                    meta if isinstance(meta, dict) else None
                )
            except Exception:
                full_auto_arms = False
    except Exception:
        homunculus_auto = False
        full_auto_arms = False
    if (
        not auto_accept_gap_gate_defaults_enabled()
        and not homunculus_auto
        and not full_auto_arms
    ):
        return False

    applied = False
    if check_gap_framing_decision_pending(ctx):
        enabled = recommended_gap_framing_enabled()
        try:
            from interview_mux.gap_fill_eligibility import (
                assess_gap_fill_eligibility,
                silent_skip_allowed,
            )

            decision = assess_gap_fill_eligibility(ctx)
            if silent_skip_allowed(decision):
                enabled = False
        except Exception:
            pass
        rec = ""
        try:
            from interview_mux.homunculus.gates import recommended_framing_action

            rec = recommended_framing_action(ctx)
        except Exception:
            rec = ""
        set_gap_framing_enabled(ctx, enabled)
        applied = True
        # Honor the set_gate_decision guard: recommended skip cannot auto_resolve.
        framing_action = "skip" if (not enabled or rec == "skip") else "auto_resolve"
        try:
            from interview_mux.homunculus.gates import try_set_gate_decision

            try_set_gate_decision(ctx, "framing_consent", framing_action)
        except Exception:
            pass
        ctx.log(
            f"Gap framing auto-accepted (defaults): {'enabled' if enabled else 'disabled'}",
            level="action",
            stage="missing_framing",
            detail={
                "kind": "gate",
                "action_id": "auto.gap_framing.accept_defaults",
                "gap_framing_enabled": enabled,
                "full_auto_arms": full_auto_arms,
                "homunculus_auto": homunculus_auto,
            },
        )

    if not gap_framing_enabled(ctx):
        return applied

    from interview_mux.source_topology import (
        check_pickup_speaker_pending,
        confirm_pickup_speaker,
    )

    if check_pickup_speaker_pending(ctx):
        try:
            from interview_mux.source_topology import resolve_clone_host_speaker_id

            host_id = resolve_clone_host_speaker_id(ctx)
            if host_id:
                confirm_pickup_speaker(ctx, speaker_id=host_id)
            else:
                raise ValueError("no_frame_speaker_for_clone")
            applied = True
            ctx.log(
                "Pickup speaker auto-confirmed (frame / question-density host)",
                level="action",
                stage="missing_framing",
                detail={"kind": "gate", "action_id": "auto.adaptation.pickup_speaker"},
            )
        except Exception as exc:
            ctx.log(
                f"Pickup speaker auto-confirm skipped: {exc}",
                level="warning",
                stage="missing_framing",
            )
            return applied

    if check_voice_reference_pending(ctx):
        from interview_mux.source_topology import (
            clone_host_auto_approve_allowed,
            resolve_clone_host_speaker_id,
        )

        speaker_id = resolve_clone_host_speaker_id(ctx) or pickup_eligible_speaker_id(ctx)
        if speaker_id and clone_host_auto_approve_allowed(ctx, speaker_id):
            try:
                from interview_mux.voice_reference import approve_voice_reference

                approve_voice_reference(ctx, speaker_id)
                applied = True
                ctx.log(
                    f"Voice reference auto-approved for {speaker_id}",
                    level="action",
                    stage="missing_framing",
                    detail={"kind": "gate", "action_id": "auto.voice_reference.approve"},
                )
            except Exception as exc:
                ctx.log(
                    f"Voice reference auto-approve skipped: {exc}",
                    level="warning",
                    stage="missing_framing",
                )
                return applied
        else:
            ctx.log(
                "no_frame_speaker_for_clone — not auto-approving voice reference",
                level="warning",
                stage="missing_framing",
                action_id="auto.voice_reference.blocked",
            )
            return applied

    if check_gap_delivery_pending(ctx):
        from interview_mux.gap_framing import gap_vo_cfg

        default = str(gap_vo_cfg().get("default_delivery", "chatterbox")).lower()
        delivery: GapVoDelivery = "chatterbox" if default == "chatterbox" else "record"
        set_gap_vo_delivery(ctx, delivery)
        applied = True
        ctx.log(
            f"Gap VO delivery auto-accepted: {delivery}",
            level="action",
            stage="missing_framing",
            detail={"kind": "gate", "action_id": "auto.gap_delivery.accept_defaults"},
        )

    if check_clone_consent_pending(ctx):
        speaker_id = pickup_eligible_speaker_id(ctx)
        if speaker_id:
            try:
                from interview_mux.mastering_voice_clone import VALID_SCOPES, grant_consent

                grant_consent(
                    ctx,
                    speaker_id=speaker_id,
                    scopes=list(VALID_SCOPES),
                    granted_by="auto_accept_defaults",
                    disclosure="none",
                )
                applied = True
                ctx.log(
                    f"Voice clone consent auto-granted for {speaker_id}",
                    level="action",
                    stage="missing_framing",
                    detail={"kind": "gate", "action_id": "auto.voice_clone.consent"},
                )
            except Exception as exc:
                ctx.log(
                    f"Voice clone consent auto-grant skipped: {exc}",
                    level="warning",
                    stage="missing_framing",
                )

    return applied


def global_gap_runtime_fields() -> dict[str, Any]:
    """Machine-global gap/VO runtime probes — cached; safe to call rarely."""
    from interview_mux.synthesis_fallback import chatterbox_runtime_available

    return {
        "chatterbox_runtime_available": chatterbox_runtime_available(),
        "auto_accept_defaults": auto_accept_gap_gate_defaults_enabled(),
    }


def gap_gate_payload_for_run(ctx: RunContext) -> dict[str, Any]:
    """Per-run gap gate fields (no subprocess probes)."""
    from interview_mux.mastering_voice_clone import consent_payload
    from interview_mux.synthesis_fallback import synthesis_fallback_notice

    llm_recommended: str | None = None
    llm_rationale: str | None = None
    if ctx.artifact_exists("understanding/framing_posture_decision.json"):
        try:
            doc = ctx.read_json("understanding/framing_posture_decision.json")
            if isinstance(doc, dict):
                llm_recommended = str(doc.get("recommended_framing") or "") or None
                llm_rationale = str(doc.get("rationale") or doc.get("summary") or "") or None
        except Exception:
            pass

    pipeline_mode: dict[str, Any] | None = None
    try:
        from interview_mux.pipeline_mode import resolve_effective_mode

        pipeline_mode = resolve_effective_mode(ctx)
    except Exception:
        pipeline_mode = None

    _ready_ok, _ready_reason = vo_path_ready(ctx, for_synthesize=False)
    _ladder_ok, _ladder_reason = vo_ladder_complete(ctx, for_synthesize=True)
    hosted_vo_floor: dict[str, Any] | None = None
    try:
        from interview_mux.hosted_vo_authority import (
            floor_identity_to_dict,
            identify_hosted_vo_floor,
        )

        hosted_vo_floor = floor_identity_to_dict(
            identify_hosted_vo_floor(ctx, persist=False)
        )
    except Exception:
        hosted_vo_floor = None
    payload = {
        **consent_payload(ctx),
        "clone_consent_required": clone_consent_required(ctx),
        "clone_consent_pending": check_clone_consent_pending(ctx),
        "gap_framing_enabled": gap_framing_enabled(ctx),
        "gap_framing_decision_pending": check_gap_framing_decision_pending(ctx),
        "recommended_gap_framing_enabled": recommended_gap_framing_enabled(),
        "llm_recommended_framing": llm_recommended,
        "llm_framing_rationale": llm_rationale,
        "pipeline_mode": pipeline_mode,
        "gap_vo_delivery": resolve_gap_vo_delivery(ctx) if gap_framing_enabled(ctx) else None,
        "gap_delivery_pending": check_gap_delivery_pending(ctx),
        "voice_reference_pending": check_voice_reference_pending(ctx),
        "voice_reference_approved": voice_reference_approved(ctx),
        "voice_reference_usable": approved_voice_reference_usable(ctx),
        "pickup_speaker_confirmed": pickup_speaker_confirmed(ctx),
        "pickup_eligible_speaker_id": pickup_eligible_speaker_id(ctx),
        "synthesis_fallback_notice": synthesis_fallback_notice(ctx),
        "vo_path_ready": {"ok": _ready_ok, "reason_code": _ready_reason},
        # G1 automation_pending ≠ ladder-complete (DP-VO1 A+).
        "vo_ladder_complete": {"ok": _ladder_ok, "reason_code": _ladder_reason},
    }
    if isinstance(hosted_vo_floor, dict):
        payload["hosted_vo_floor"] = hosted_vo_floor
    return payload


def gap_gate_payload(ctx: RunContext) -> dict[str, Any]:
    """Full gap gate payload for dedicated gap-framing API routes."""
    return {**gap_gate_payload_for_run(ctx), **global_gap_runtime_fields()}
