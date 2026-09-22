"""Shared delivery thrash invariants (post-exec_10066 hardening).

Named helpers for committed-vs-pending honesty, remutate protect, seed-order
restamp, and seed-cycle detection. Call sites must prefer these over ad-hoc
``artifact_exists("master/master.wav")`` / listen-delight-only protect lists.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Literal

from interview_mux.run_context import RunContext

INVARIANT_HEALS_REL = "operator/invariant_heals.jsonl"
SEED_RESUME_LEDGER_REL = "operator/seed_resume_ledger.json"
VO_LINE_OWNERS_REL = "operator/vo_line_owners.json"

# C-01 owners: drives stability / incompleteness / resume (one table).
OWNER_RECORD = "vo_line_adjudicate"
OWNER_SYNTH = "vo_synthesize"
OWNER_SKIPPED = "skipped"
OWNER_OMITTED = "omitted"

# Remutate plan artifacts that clear markers — union for orphan-promote protect.
REMUTATE_PLAN_RELS: tuple[str, ...] = (
    "mastering/listen_delight_remutate.json",
    "mastering/edl_narrative_remutate.json",
)

SeedHealAction = Literal["restamp", "unmark"]


def committed_path_exists(ctx: RunContext, *parts: str) -> bool:
    """True only when the committed final path exists (never pending shadow)."""
    try:
        return ctx.final_path(*parts).is_file()
    except Exception:
        return False


def committed_master_wav(ctx: RunContext) -> bool:
    return committed_path_exists(ctx, "master", "master.wav")


# Floor for a non-truncated master export (PCM WAV header + payload).
MIN_COMMITTED_MASTER_BYTES = 8_192
_MIN_COMMITTED_MASTER_BYTES = MIN_COMMITTED_MASTER_BYTES  # compat alias


def committed_master_integrity_ok(ctx: RunContext) -> bool:
    """End-E: committed master.wav must exist and pass size floor.

    Truncated loudnorm / empty RIFF stubs must not count as live finalize authority.
    Pending-only shadows never satisfy this check (``final_path`` must exist).
    """
    try:
        path = ctx.final_path("master", "master.wav")
        if not path.is_file():
            return False
        return path.stat().st_size >= MIN_COMMITTED_MASTER_BYTES
    except Exception:
        return False


def parse_seed_order_producer(message: str) -> str | None:
    """Extract the named incomplete producer from seed-order prose.

    ``seed order: complete <producer> before running <consumer>`` → producer.
    Never invent ``edl`` / ``mix`` / ``master_finalize`` as a default pin.
    """
    import re

    text = str(message or "")
    m = re.search(r"complete\s+(\S+)\s+before", text, flags=re.IGNORECASE)
    if not m:
        return None
    raw = str(m.group(1) or "").strip().strip(".:;")
    if not raw or raw.lower() in {"seed_order", "seed_order_prereq"}:
        return None
    return raw


def live_producer_authority(ctx: RunContext, stage: str) -> bool:
    """True when re-running ``stage`` would orphan live expensive artifacts."""
    stage = str(stage or "").strip()
    if not stage:
        return False
    try:
        if stage == "sound_design_plan":
            from interview_mux.homunculus.agenda import delivery_sdp_present

            return bool(delivery_sdp_present(ctx))
        if stage in {
            "music_palette_compose",
            "sfx_prompt_craft",
            "mmaudio_sfx",
        }:
            from interview_mux.delivery_guardrails import music_epoch_complete

            return bool(music_epoch_complete(ctx))
        if stage in {"mix", "assembly_preview"}:
            return committed_path_exists(ctx, "master", "assembly.wav") or (
                stage == "assembly_preview"
                and committed_path_exists(ctx, "master", "assembly_preview.wav")
            )
        if stage == "vo_line_adjudicate":
            from interview_mux.delivery_guardrails import (
                seed_stage_complete,
                seal_adjudicate_stale_when_g1_green,
            )
            from interview_mux.gates import check_g1_vo

            # G1 green ⇒ refuse re-adjudicate / WAV purge (anti-thrash).
            # G1 green ≠ seed_complete for music/seal — authority for restamp
            # requires seed_complete so consumers do not treat adjudicate as ready.
            seal_adjudicate_stale_when_g1_green(ctx)
            if seed_stage_complete(ctx, "vo_line_adjudicate"):
                return True
            # Still seal stale when G1 green (anti-purge), but not live authority
            # for restamp-as-ready toward music consumers.
            if not check_g1_vo(ctx):
                return False
            return False
        if stage == "master_finalize":
            # End-E: file presence alone is not live authority — integrity required.
            return committed_master_integrity_ok(ctx)
    except Exception:
        return False
    return False


def seed_order_consumer_for(ctx: RunContext, pin: str, *, message: str = "") -> str:
    """Resume consumer after restamping a live producer pin."""
    pin = str(pin or "").strip()
    low = (message or "").lower()
    # Prefer consumer named in the seed-order error ("complete X before Y").
    if "before running " in low:
        try:
            tail = low.split("before running ", 1)[1]
            consumer = tail.split()[0].strip(".:;")
            if consumer and consumer != pin:
                # SDP → never jump to mix while music epoch incomplete.
                if pin == "sound_design_plan" and consumer == "mix":
                    try:
                        from interview_mux.delivery_guardrails import (
                            MUSIC_BEFORE_MIX,
                            music_epoch_complete,
                            seed_stage_complete,
                        )

                        if not music_epoch_complete(ctx):
                            for sid in MUSIC_BEFORE_MIX:
                                if not seed_stage_complete(ctx, sid):
                                    return sid
                    except Exception:
                        pass
                return consumer
        except Exception:
            pass
    # sound_design_plan restamp → earliest incomplete MUSIC_BEFORE_MIX (not mix).
    if pin == "sound_design_plan":
        try:
            from interview_mux.delivery_guardrails import (
                MUSIC_BEFORE_MIX,
                music_epoch_complete,
                seed_stage_complete,
            )

            if not music_epoch_complete(ctx):
                for sid in MUSIC_BEFORE_MIX:
                    if not seed_stage_complete(ctx, sid):
                        return sid
        except Exception:
            pass
    defaults = {
        "sound_design_plan": "mix",
        "music_palette_compose": "sfx_prompt_craft",
        "sfx_prompt_craft": "mmaudio_sfx",
        "mmaudio_sfx": "mix",
        "assembly_preview": "mix",
        "mix": "junction_snip_qa",
        "vo_line_adjudicate": "vo_synthesize",
        "master_finalize": "master_transcript_build",
    }
    return defaults.get(pin, pin)


def seed_order_heal_action(
    ctx: RunContext, pin: str, *, message: str = ""
) -> tuple[SeedHealAction, str]:
    """Return (restamp|unmark, resume_stage) for a seed-order pin.

    End-E: ``master_finalize`` without integrity never restamps — unmark and
    re-run finalize so truncated/pending masters cannot soft-complete ship.
    """
    pin = str(pin or "").strip()
    if pin == "master_finalize" and not committed_master_integrity_ok(ctx):
        return "unmark", pin
    if live_producer_authority(ctx, pin):
        return "restamp", seed_order_consumer_for(ctx, pin, message=message)
    return "unmark", pin


def _remutate_plan_active(doc: dict[str, Any]) -> bool:
    if doc.get("exhausted"):
        return False
    attempt = int(doc.get("attempt") or 0)
    max_attempts = int(doc.get("max_attempts") or 3)
    if attempt > max_attempts:
        return False
    return True


def active_remutate_stages(ctx: RunContext) -> frozenset[str]:
    """Stages cleared by any in-flight remutate — do not orphan-promote.

    Only stages at/after the plan ``from_stage`` are cleared. Earlier entries in
    ``from_stages`` are advisory producers for a full rebuild when the pin is
    early (e.g. edl); when the pin is ``junction_snip_qa``, clearing
    ``air_script_seams`` left seed-order blocking the remutate target
    (forensics exec_11130).
    """
    from interview_mux.refinement_passes import filter_retired_refine_stages
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    order = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    index = {sid: i for i, sid in enumerate(order)}
    out: set[str] = set()
    for rem_rel in REMUTATE_PLAN_RELS:
        try:
            if not ctx.artifact_exists(rem_rel):
                continue
            rem = ctx.read_json(rem_rel)
            if not isinstance(rem, dict) or not _remutate_plan_active(rem):
                continue
            pin = str(rem.get("from_stage") or "").strip()
            pin_i = index.get(pin)
            for sid in filter_retired_refine_stages(rem.get("from_stages") or []):
                sid_s = str(sid or "").strip()
                if not sid_s:
                    continue
                if pin_i is not None:
                    sid_i = index.get(sid_s)
                    if sid_i is not None and sid_i < pin_i:
                        continue
                out.add(sid_s)
            if pin:
                out.add(pin)
        except Exception:
            continue
    return frozenset(out)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_invariant_heal(
    ctx: RunContext,
    *,
    kind: str,
    stage: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    """Append one row to operator/invariant_heals.jsonl (best-effort)."""
    try:
        path = ctx.final_path(*INVARIANT_HEALS_REL.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": _utc_now(),
            "kind": kind,
            "stage": stage,
            "detail": detail or {},
        }
        with path.open("a", encoding="utf-8") as fh:
            import json

            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def note_seed_resume(
    ctx: RunContext,
    *,
    from_stage: str,
    because_of: str = "",
    fingerprint: str = "",
) -> dict[str, Any]:
    """Record a seed/heal resume for cycle detection."""
    from_stage = str(from_stage or "").strip()
    because_of = str(because_of or "").strip()
    fingerprint = str(fingerprint or "").strip()
    doc: dict[str, Any] = {"version": 1, "resumes": []}
    try:
        if ctx.artifact_exists(SEED_RESUME_LEDGER_REL):
            loaded = ctx.read_json(SEED_RESUME_LEDGER_REL)
            if isinstance(loaded, dict):
                doc = loaded
    except Exception:
        pass
    resumes = list(doc.get("resumes") or [])
    resumes.append(
        {
            "ts": _utc_now(),
            "from_stage": from_stage,
            "because_of": because_of,
            "fingerprint": fingerprint,
        }
    )
    doc["resumes"] = resumes[-40:]
    try:
        ctx.write_json(SEED_RESUME_LEDGER_REL, doc, skip_handoff=True)
    except Exception:
        pass
    return doc


def detect_seed_cycle(
    ctx: RunContext,
    *,
    from_stage: str,
    because_of: str = "",
    fingerprint: str = "",
    window: int = 6,
) -> bool:
    """True when resumes oscillate A↔B with unchanged fingerprint."""
    from_stage = str(from_stage or "").strip()
    because_of = str(because_of or "").strip()
    fingerprint = str(fingerprint or "").strip()
    try:
        if not ctx.artifact_exists(SEED_RESUME_LEDGER_REL):
            return False
        doc = ctx.read_json(SEED_RESUME_LEDGER_REL)
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    resumes = [r for r in (doc.get("resumes") or []) if isinstance(r, dict)]
    if len(resumes) < 4:
        return False
    recent = resumes[-window:]
    stages = [str(r.get("from_stage") or "") for r in recent]
    fps = [str(r.get("fingerprint") or "") for r in recent]
    # Need A B A B pattern with same fingerprint (or empty fp).
    if len(set(stages)) != 2:
        return False
    a, b = stages[0], stages[1]
    if a == b or not a or not b:
        return False
    expected = [a, b] * (len(stages) // 2)
    if stages[: len(expected)] != expected and stages != [a, b, a, b][: len(stages)]:
        # Allow either starting with a or checking alternation
        alt_ok = all(
            stages[i] == (a if i % 2 == 0 else b) for i in range(len(stages))
        ) or all(stages[i] == (b if i % 2 == 0 else a) for i in range(len(stages)))
        if not alt_ok:
            return False
    if fingerprint:
        if any(fp and fp != fingerprint for fp in fps[-4:]):
            return False
    elif len(set(fps[-4:])) > 1 and any(fps[-4:]):
        return False
    # Also require because_of pairing when present
    if because_of and from_stage:
        pair = {from_stage, because_of}
        if not pair.issubset(set(stages)):
            # still a cycle on stages alone
            pass
    record_invariant_heal(
        ctx,
        kind="seed_cycle_detected",
        stage=from_stage,
        detail={"because_of": because_of, "stages": stages[-6:], "fingerprint": fingerprint},
    )
    return True


def count_identical_seed_resumes(
    ctx: RunContext,
    *,
    from_stage: str,
    fingerprint: str,
    window: int = 8,
) -> int:
    """Count recent resumes with the same from_stage + fingerprint."""
    from_stage = str(from_stage or "").strip()
    fingerprint = str(fingerprint or "").strip()
    try:
        if not ctx.artifact_exists(SEED_RESUME_LEDGER_REL):
            return 0
        doc = ctx.read_json(SEED_RESUME_LEDGER_REL)
    except Exception:
        return 0
    if not isinstance(doc, dict):
        return 0
    resumes = [r for r in (doc.get("resumes") or []) if isinstance(r, dict)]
    recent = resumes[-window:]
    return sum(
        1
        for r in recent
        if str(r.get("from_stage") or "") == from_stage
        and str(r.get("fingerprint") or "") == fingerprint
    )


def sync_vo_line_owners(ctx: RunContext) -> dict[str, Any]:
    """C-01: Persist ``{line_id → owner}`` + gap/seats fingerprint.

    Owners:
    - skipped / omitted → never G1 or synth
    - delivery=record (open) → vo_line_adjudicate
    - delivery=synthesize (open) → vo_synthesize
    """
    import hashlib
    import json

    owners: dict[str, str] = {}
    gap_fp = ""
    try:
        if ctx.artifact_exists("understanding/gap_report.json"):
            gap = ctx.read_json("understanding/gap_report.json") or {}
            gap_fp = hashlib.sha256(
                json.dumps(gap, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()[:16]
            for row in gap.get("interviewer_lines") or []:
                if not isinstance(row, dict):
                    continue
                lid = str(row.get("line_id") or "").strip()
                if not lid:
                    continue
                if row.get("skipped_optional") or row.get("air_script_omit"):
                    owners[lid] = OWNER_SKIPPED
                    continue
                try:
                    from interview_mux.omit_ledger import (
                        OMIT_LEDGER_REL,
                        effective_air_contract,
                    )

                    ledger = (
                        ctx.read_json(OMIT_LEDGER_REL)
                        if ctx.artifact_exists(OMIT_LEDGER_REL)
                        else None
                    )
                    contract = effective_air_contract(
                        ledger,
                        line_id=lid,
                        target_segment_id=str(row.get("targets_segment_id") or "")
                        or None,
                    )
                    if contract.get("status") in ("omitted", "deferred", "suppressed"):
                        owners[lid] = OWNER_OMITTED
                        continue
                except Exception:
                    pass
                delivery = str(row.get("delivery") or "synthesize").strip().lower()
                if delivery == "record":
                    owners[lid] = OWNER_RECORD
                else:
                    owners[lid] = OWNER_SYNTH
    except Exception:
        owners = {}
    doc = {
        "version": 1,
        "fingerprint": gap_fp,
        "owners": owners,
        "updated_at": _utc_now(),
    }
    try:
        ctx.write_json(VO_LINE_OWNERS_REL, doc, skip_handoff=True)
    except Exception:
        pass
    return doc


def resolve_g1_vo_open_resume(ctx: RunContext) -> str:
    """Single resume policy for g1_vo_open (Wave 1 / C-01).

    - Full-auto: rewrite record→synthesize first (VS-B3), then resume as synth.
    - Record G1 open (manual/partial) → never seed-heal into synth loop
      (pin adjudicate/operator).
    - Synth G1 + adjudicate seeded (seed-complete **or** done+gap present) → vo_synthesize
    - Synth G1 + adjudicate hollow / ambiguous → vo_line_adjudicate
    - Same fingerprint bounce adjudicate↔synth → stick on vo_synthesize
    """
    try:
        from interview_mux.gap_vo_gates import rewrite_full_auto_record_lines_to_synth

        rewrite_full_auto_record_lines_to_synth(ctx)
    except Exception:
        pass
    owners_doc = sync_vo_line_owners(ctx)
    owners = owners_doc.get("owners") if isinstance(owners_doc, dict) else {}
    if not isinstance(owners, dict):
        owners = {}
    open_owners = {
        lid: own
        for lid, own in owners.items()
        if own in {OWNER_RECORD, OWNER_SYNTH}
    }
    # Missing WAVs / G1 holes: prefer owner table when present.
    record_open = [lid for lid, own in open_owners.items() if own == OWNER_RECORD]
    synth_open = [lid for lid, own in open_owners.items() if own == OWNER_SYNTH]

    from interview_mux.delivery_guardrails import (
        _g1_record_open,
        seed_stage_complete,
    )

    if record_open or _g1_record_open(ctx):
        # Operator/record path — never seed-heal into synth loop.
        resume = OWNER_RECORD
    else:
        adjudicate_seeded = False
        try:
            adjudicate_seeded = bool(seed_stage_complete(ctx, "vo_line_adjudicate"))
        except Exception:
            adjudicate_seeded = False
        if not adjudicate_seeded:
            try:
                adjudicate_seeded = bool(
                    ctx.is_done("vo_line_adjudicate")
                    and ctx.artifact_exists("understanding/gap_report.json")
                )
            except Exception:
                adjudicate_seeded = False
        if adjudicate_seeded or synth_open:
            resume = OWNER_SYNTH
        else:
            resume = OWNER_RECORD

    # C-01: refuse adjudicate↔synth bounce on unchanged fingerprint.
    fp = str(owners_doc.get("fingerprint") or "")
    try:
        if detect_seed_cycle(
            ctx, from_stage=resume, because_of="g1_vo_open", fingerprint=fp
        ):
            resume = OWNER_SYNTH
            record_invariant_heal(
                ctx,
                kind="g1_resume_bounce_stick_synth",
                stage=resume,
                detail={"fingerprint": fp},
            )
        # Sticky: recent resume already on synth with same fp → stay (no bounce).
        n = count_identical_seed_resumes(
            ctx, from_stage=OWNER_SYNTH, fingerprint=fp, window=4
        )
        if n >= 1 and resume == OWNER_RECORD and not record_open:
            resume = OWNER_SYNTH
    except Exception:
        pass
    return resume


def invariant_fire_summary(ctx: RunContext) -> dict[str, int]:
    """Counts of invariant heals by kind (for DECISION summary / forensics)."""
    counts: dict[str, int] = {}
    try:
        path = ctx.final_path(*INVARIANT_HEALS_REL.split("/"))
        if not path.is_file():
            return counts
        import json

        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            kind = str((row or {}).get("kind") or "unknown")
            counts[kind] = counts.get(kind, 0) + 1
    except Exception:
        pass
    return counts


def apply_seed_order_heal(
    ctx: RunContext,
    pin: str,
    *,
    message: str = "",
    unmark_fn: Callable[[RunContext, str], None] | None = None,
) -> str:
    """Restamp or unmark per live authority; return resume stage."""
    action, resume = seed_order_heal_action(ctx, pin, message=message)
    if action == "restamp":
        try:
            marker = ctx.run_dir / ".stage_done" / pin
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
        except Exception:
            pass
        record_invariant_heal(
            ctx,
            kind="seed_order_restamp",
            stage=pin,
            detail={"resume": resume, "message": (message or "")[:160]},
        )
        return resume
    if unmark_fn is not None:
        try:
            unmark_fn(ctx, pin)
        except Exception:
            pass
    else:
        try:
            marker = ctx.run_dir / ".stage_done" / pin
            marker.unlink(missing_ok=True)
        except Exception:
            pass
    return resume
