"""Shared helpers for isolated run directories (import as `from run_fixtures import ...`)."""

from __future__ import annotations

import json
import math
import shutil
import struct
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

MINIMAL_WAV_BYTES = b"RIFF" + b"\x00" * 64


def mark_done_raw(ctx: RunContext, *stages: str) -> None:
    """TH1b: fixture hollow stamp — touch ``.stage_done`` markers without heal/completeness gates.

    Prefer this over ``mark_done(..., force=True)`` in fixtures so partial/incomplete
    artifacts (e.g. bare master.wav) do not block the stamp, while production
    ``mark_done`` still refuses incomplete artifacts.
    """
    for sid in stages:
        if not sid:
            continue
        marker = ctx.final_path(".stage_done", str(sid))
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()


def write_fixture_vo_wav(path: Path, *, duration_sec: float = 0.6) -> None:
    """Write a short speech-like WAV G1 can resolve (committed tree, not staging)."""
    rate = 16000
    n = max(1, int(rate * duration_sec))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        samples: list[int] = []
        for i in range(n):
            t = i / rate
            env = 0.4 + 0.4 * abs(math.sin(2 * math.pi * 5 * t))
            voiced = (
                0.55 * math.sin(2 * math.pi * 180 * t)
                + 0.3 * math.sin(2 * math.pi * 850 * t)
                + 0.15 * math.sin(2 * math.pi * 2200 * t)
            )
            samples.append(int(max(-32767, min(32767, 11000 * env * voiced))))
        wf.writeframes(struct.pack(f"<{n}h", *samples))


def write_fixture_json(
    ctx: RunContext,
    rel: str,
    data: Any,
    *,
    stage_key: str | None = None,
    role: str = "ops",
) -> Path:
    """Plant JSON on the committed tree without going through ownership assert_write.

    ``ctx.write_json`` always runs ``assert_write`` even with ``skip_handoff=True``.
    Tests must plant via file_store or an owner ``stage_key``; this helper is the
    file_store path. ``stage_key`` / ``role`` are accepted for call-site clarity
    and unused by the write itself.
    """
    _ = (stage_key, role)
    from interview_mux.file_store import write_json as fs_write_json

    path = ctx.final_path(*_rel_parts(rel))
    fs_write_json(path, data)
    return path


def write_fixture_bytes(ctx: RunContext, rel: str, data: bytes) -> Path:
    path = ctx.final_path(*_rel_parts(rel))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _rel_parts(rel: str) -> tuple[str, ...]:
    return tuple(p for p in str(rel or "").replace("\\", "/").lstrip("/").split("/") if p)


def write_fixture_theme_wav(ctx: RunContext, rel: str, *, duration_sec: float = 1.2) -> Path:
    """Audible theme WAV (speech-free beds reject stub / digital-silence)."""
    path = ctx.final_path(*_rel_parts(rel))
    write_fixture_vo_wav(path, duration_sec=duration_sec)
    return path


def confirm_test_pickup_speaker(ctx: RunContext, speaker_id: str = "spk_host") -> None:
    """Stamp G1 pickup confirm the way production reads it (no operator GUI)."""
    sid = str(speaker_id or "spk_host").strip() or "spk_host"
    topo: dict[str, Any] = {}
    if ctx.artifact_exists("understanding/source_topology.json"):
        try:
            existing = ctx.read_json("understanding/source_topology.json")
            if isinstance(existing, dict):
                topo = dict(existing)
        except Exception:
            topo = {}
    stats = list(topo.get("speaker_stats") or [])
    known = {str(r.get("speaker_id") or "") for r in stats if isinstance(r, dict)}
    if sid not in known:
        stats.append({"speaker_id": sid, "role": "interviewer", "talk_time_ms": 5_000})
        if "spk_guest" not in known and sid != "spk_guest":
            stats.append(
                {"speaker_id": "spk_guest", "role": "interviewee", "talk_time_ms": 90_000}
            )
    topo.setdefault("topology_class", "one_on_one_asymmetric")
    topo["pickup_eligible_speaker_id"] = sid
    topo["least_spoken_speaker_id"] = sid
    topo["speaker_stats"] = stats
    write_fixture_json(ctx, "understanding/source_topology.json", topo)

    adapt: dict[str, Any] = {}
    if ctx.artifact_exists("understanding/flow_adaptation.json"):
        try:
            existing = ctx.read_json("understanding/flow_adaptation.json")
            if isinstance(existing, dict):
                adapt = dict(existing)
        except Exception:
            adapt = {}
    overrides = dict(adapt.get("operator_overrides") or {})
    overrides["pickup_speaker_confirmed"] = True
    adapt["operator_overrides"] = overrides
    adapt["pickup_eligible_speaker_id"] = sid
    adapt.setdefault("topology_class", topo.get("topology_class") or "one_on_one_asymmetric")
    write_fixture_json(ctx, "understanding/flow_adaptation.json", adapt)


def _with_producer(doc: dict[str, Any], stage_id: str) -> dict[str, Any]:
    out = dict(doc)
    meta = dict(out.get("_meta") or {})
    meta["producer_stage"] = str(stage_id)
    out["_meta"] = meta
    return out


def minimal_nugget_corpus(**patch: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "nuggets": [
            {
                "nugget_id": "nug_001",
                "text_claim": "The guest explains the origin story.",
                "evidence_quote": "A useful guest quote about the origin story.",
                "in_selection": True,
                "source_segment_ids": ["seg_001"],
                "speaker_id": "spk_guest",
                "source_start_ms": 0,
                "source_end_ms": 4000,
            }
        ]
    }
    base.update(patch)
    return base


def minimal_information_packages_audit(**patch: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": 1,
        "status": "complete",
        "packages": [],
        "episode_close": {
            "music": {
                "required": True,
                "role": "theme_outro",
                "placement": "after_last_native",
            }
        },
    }
    base.update(patch)
    return base


def minimal_nugget_layup_plan(**patch: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ordered_segment_ids": ["seg_001"],
        "layups": [{"target_segment_id": "seg_001", "skip": True, "skip_reason_code": "fixture"}],
    }
    base.update(patch)
    return base


def minimal_vo_synthesize(**patch: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": 1,
        "status": "complete",
        "lines": [],
        "skipped": True,
        "reason": "fixture_no_vo_lines",
    }
    base.update(patch)
    return base


def minimal_edl(**patch: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "version": 1,
        "ordered_segment_ids": ["seg_001"],
        "timeline_duration_ms": 5000,
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_001",
                "source_start_ms": 0,
                "source_end_ms": 5000,
                "timeline_start_ms": 0,
                "duration_ms": 5000,
            }
        ],
    }
    base.update(patch)
    return base


def minimal_mastering_plan(**patch: Any) -> dict[str, Any]:
    from interview_mux.mastering_plan_loader import forced_sparse_plan

    base = forced_sparse_plan(reason="pytest fixture seed-complete")
    base["air_script"] = {"pass": "pass_b", "beats": []}
    base.update(patch)
    return base


def minimal_transitions(**patch: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "transitions": [],
        "selection_count": 1,
        "empty_ok": True,
    }
    base.update(patch)
    return base


def plant_shared_delivery_lattice(ctx: RunContext) -> None:
    """Shared selection / transitions / corpus so MUST_PRECEDE hops can land."""
    if not ctx.artifact_exists("master/selection.json"):
        write_fixture_json(
            ctx,
            "master/selection.json",
            _with_producer(minimal_master_selection(), "selection_order_sanitize"),
        )
    if not ctx.artifact_exists("master/transitions.json"):
        write_fixture_json(
            ctx,
            "master/transitions.json",
            _with_producer(minimal_transitions(), "transitions"),
        )
    if not ctx.artifact_exists("understanding/nugget_corpus.json"):
        write_fixture_json(ctx, "understanding/nugget_corpus.json", minimal_nugget_corpus())
    if not ctx.artifact_exists("segments/manifest.json"):
        write_fixture_json(ctx, "segments/manifest.json", minimal_manifest())
    if not ctx.artifact_exists("understanding/gap_report.json"):
        write_fixture_json(
            ctx,
            "understanding/gap_report.json",
            _with_producer(seed_complete_gap_report(), "gap_framing_compose"),
        )


def _plant_primary_payload(ctx: RunContext, stage_id: str) -> None:
    """Write a seed-complete-enough primary (+ extras) for ``stage_id``."""
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    sid = str(stage_id or "").strip()
    rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)

    extras: dict[str, Any] = {
        "information_package_plan": (
            "mastering/shape/information_packages_audit.json",
            minimal_information_packages_audit(),
        ),
        "nugget_corpus_mine": ("understanding/nugget_corpus.json", minimal_nugget_corpus()),
        "nugget_layup_compose": (
            "understanding/nugget_layup_plan.json",
            minimal_nugget_layup_plan(),
        ),
        "gap_report_sanitize": (
            "understanding/gap_report.json",
            _with_producer(seed_complete_gap_report(), "gap_report_sanitize"),
        ),
        "refinement_agenda": (
            "understanding/refinement_agenda.json",
            {"schema_version": 1, "items": [], "status": "complete"},
        ),
        "gap_framing_recompose": (
            "understanding/gap_framing_recompose.json",
            {"skipped": True, "reason": "fixture"},
        ),
        "selection_framing_apply": (
            "understanding/selection_framing_apply.json",
            {"skipped": True, "reason": "fixture"},
        ),
        "air_script_seams": (
            "mastering/mastering_plan.json",
            _with_producer(minimal_mastering_plan(), "air_script_seams"),
        ),
        "air_contract_sanitize": (
            "mastering/mastering_plan.json",
            _with_producer(minimal_mastering_plan(), "air_contract_sanitize"),
        ),
        "air_script_compose": (
            "mastering/mastering_plan.json",
            _with_producer(minimal_mastering_plan(), "air_script_compose"),
        ),
        "transitions": (
            "master/transitions.json",
            _with_producer(minimal_transitions(), "transitions"),
        ),
        "vo_line_adjudicate": (
            "understanding/vo_line_adjudication.json",
            {"lines": []},
        ),
        "vo_synthesize": ("mastering/vo_synthesize.json", minimal_vo_synthesize()),
        "sound_design_vo_finalize": (
            "mastering/sound_design_vo_finalize.json",
            {"skipped": True, "refused": False, "reason": "fixture"},
        ),
        "edl_narrative_audit": (
            "master/edl_narrative_audit.json",
            {
                "verdict": "pass",
                "blocking_issues": [],
                "warnings": [],
                "recommended_actions": [],
                "reasoning_summary": "Fixture narrative audit pass.",
            },
        ),
        "edl": ("master/edl.json", _with_producer(minimal_edl(), "edl")),
        "full_master_ranking": (
            "master/selection.json",
            _with_producer(minimal_master_selection(), "full_master_ranking"),
        ),
        "selection_order_sanitize": (
            "master/selection.json",
            _with_producer(minimal_master_selection(), "selection_order_sanitize"),
        ),
        "narrative_arc_plan": ("master/narrative_plan.json", minimal_narrative_plan()),
        "chapter_close_hitch": (
            "mastering/chapter_close_hitch.json",
            {"schema_version": 1, "status": "complete", "hitches": []},
        ),
        "connector_fuse_pass_pre_ranking": (
            "analysis/connector_fuse_rounds_pre_ranking.json",
            {"pass_id": "pre_ranking", "rounds": [], "status": "complete"},
        ),
        "listen_delight_audit": (
            "mastering/listen_delight_audit.json",
            {"schema_version": 1, "status": "pass", "findings": []},
        ),
        "music_palette_compose": (
            "sound_design/music_palette_compose.json",
            {"schema_version": 1, "status": "complete", "assets": []},
        ),
        "sfx_prompt_craft": (
            "sound_design/sfx_prompts.json",
            {"prompts": []},
        ),
        "mmaudio_sfx": (
            "sound_design/mmaudio_qa.json",
            {"schema_version": 1, "assets": [], "status": "complete"},
        ),
        "junction_snip_qa": (
            "master/junction_snip_qa.json",
            {"schema_version": 1, "status": "pass", "seams": []},
        ),
        "gap_framing_compose": ("understanding/gap_report.json", seed_complete_gap_report()),
        "missing_framing": ("understanding/gap_evaluations.json", minimal_gap_evaluations()),
        "source_topology_build": (
            "understanding/source_topology.json",
            {
                "topology_class": "one_on_one_asymmetric",
                "pickup_eligible_speaker_id": "spk_host",
                "least_spoken_speaker_id": "spk_host",
                "speaker_stats": [
                    {"speaker_id": "spk_host", "role": "interviewer", "talk_time_ms": 5_000},
                    {"speaker_id": "spk_guest", "role": "interviewee", "talk_time_ms": 90_000},
                ],
            },
        ),
        "audio_preclean": None,
        "ingest": None,
        "assembly_preview": None,
        "mix": None,
        "master_finalize": None,
    }

    if sid == "sound_design_plan":
        plan = sound_design_plan_with(
            coherence={
                "sonic_identity": "warm dry close-mic room",
                "primary_mood": "intimate",
                "density": "sparse",
            }
        )
        plan["_meta"] = {"producer_stage": "sound_design_plan"}
        write_fixture_json(ctx, "understanding/sound_design_plan.json", plan)
        if not ctx.artifact_exists("master/transitions.json"):
            write_fixture_json(
                ctx,
                "master/transitions.json",
                _with_producer(minimal_transitions(), "transitions"),
            )
        return

    if sid == "audio_preclean":
        write_fixture_json(
            ctx,
            "preclean/skip.json",
            {"skipped": True, "reason": "fixture", "provider": "none"},
        )
        return

    if sid in {"ingest", "mix", "assembly_preview", "master_finalize"}:
        wav_rel = {
            "ingest": "ingest/normalized.wav",
            "mix": "master/assembly.wav",
            "assembly_preview": "master/assembly_preview.wav",
            "master_finalize": "master/master.wav",
        }[sid]
        write_fixture_theme_wav(ctx, wav_rel)
        if sid == "junction_snip_qa" or sid == "mix":
            pass
        return

    if sid == "junction_snip_qa":
        write_fixture_json(
            ctx,
            "master/junction_snip_qa.json",
            {"schema_version": 1, "status": "pass", "seams": []},
        )
        write_fixture_json(
            ctx,
            "master/seam_autopsy.json",
            {"schema_version": 1, "status": "pass", "seams": []},
        )
        if not ctx.artifact_exists("master/assembly.wav"):
            write_fixture_theme_wav(ctx, "master/assembly.wav")
        return

    spec = extras.get(sid)
    if spec is not None:
        path, payload = spec
        write_fixture_json(ctx, path, payload)
        if sid == "information_package_plan" and not ctx.artifact_exists(
            "understanding/nugget_corpus.json"
        ):
            write_fixture_json(ctx, "understanding/nugget_corpus.json", minimal_nugget_corpus())
        if sid == "edl" and not ctx.artifact_exists("master/selection.json"):
            write_fixture_json(ctx, "master/selection.json", minimal_master_selection())
        return

    if rel:
        if rel.endswith(".wav") or rel.endswith(".mp3") or rel.endswith(".jpg"):
            if rel.endswith(".wav"):
                write_fixture_theme_wav(ctx, rel)
            else:
                write_fixture_bytes(ctx, rel, b"\xff\xd8\xff" + b"\x00" * 64)
            return
        write_fixture_json(ctx, rel, {"schema_version": 1, "status": "complete", "fixture": True})


def plant_primary_and_stamp(ctx: RunContext, stage_id: str) -> None:
    """Write a schema-enough primary then hollow-stamp ``.stage_done``."""
    sid = str(stage_id or "").strip()
    if not sid:
        return
    plant_shared_delivery_lattice(ctx)
    _plant_primary_payload(ctx, sid)
    mark_done_raw(ctx, sid)


def plant_seed_complete_through(ctx: RunContext, stage_id: str) -> None:
    """Walk MUST_PRECEDE from ``stage_id`` back to roots and plant each hop."""
    from interview_mux.delivery_guardrails import MUST_PRECEDE

    sid = str(stage_id or "").strip()
    if not sid:
        return
    plant_shared_delivery_lattice(ctx)
    ordered: list[str] = []
    seen: set[str] = set()

    def _walk(cur: str) -> None:
        if not cur or cur in seen:
            return
        seen.add(cur)
        for pred in MUST_PRECEDE.get(cur, ()):
            _walk(str(pred))
        ordered.append(cur)

    _walk(sid)
    for hop in ordered:
        plant_primary_and_stamp(ctx, hop)


# Stable hash pair for reuse tests (same source audio fingerprint).
TEST_SOURCE_AUDIO_HASH = "a" * 64
TEST_SOURCE_AUDIO_HASH_SHORT = "a" * 12

_MERGED_CONFIG_MODULES = (
    "interview_mux.config",
    "interview_mux.run_context",
    "interview_mux.stage_execution_reuse",
    "interview_mux.web.server",
    "interview_mux.gui_session",
    "interview_mux.write_staging",
    "interview_mux.llm_call_record",
    "interview_mux.llm_calls_gui",
    "interview_mux.journey_state",
    "interview_mux.session_lineage",
    "interview_mux.llm_flow_hardening",
    "interview_mux.llm_preflight",
    "interview_mux.gates",
    "interview_mux.stages.sound_design_stages",
    "interview_mux.artifact_cross_validate",
    "interview_mux.artifact_auto_resolve",
    "interview_mux.config",
    "interview_mux.null_field_policy",
    "interview_mux.llm_fabricate",
    "interview_mux.llm_output_normalizer",
    "interview_mux.llm_output_resilience",
    "interview_mux.soundscape_policy",
    "interview_mux.creative_delivery",
    "interview_mux.soundscape_verify",
    "interview_mux.sound_design",
    "interview_mux.placement_qa",
)


def patch_mix_test_config(
    monkeypatch,
    *,
    disable_soundscape: bool = True,
    disable_creative_delivery: bool = True,
) -> None:
    """Isolate mix tests from creative-delivery density gates and soundscape verify."""
    from interview_mux.config import merged_config

    base = merged_config()
    overrides: dict[str, Any] = {**base}
    if disable_soundscape:
        overrides["soundscape"] = {
            **(base.get("soundscape") or {}),
            "enabled": False,
            "fail_closed": False,
        }
    if disable_creative_delivery:
        overrides["creative_delivery"] = {
            **(base.get("creative_delivery") or {}),
            "required": False,
        }
    mix_cfg = dict(base.get("mix") or {})
    intel = dict(mix_cfg.get("intelligibility_qc") or {})
    intel["remux_on_fail"] = False
    mix_cfg["intelligibility_qc"] = intel
    mix_cfg["bed_presence_qc"] = {"enabled": False, "fail_closed": False}
    overrides["mix"] = mix_cfg
    sd = dict(base.get("sound_design") or {})
    sd["block_mix_on_mmaudio_qa_fail"] = False
    overrides["sound_design"] = sd
    patch_merged_config(monkeypatch, overrides)

def parse_log_detail(entry: dict[str, Any]) -> dict[str, Any]:
    """Return inner detail dict from gui_log.jsonl entry (handles operator_log envelope)."""
    raw = entry.get("detail")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"detail": raw}
        return parsed if isinstance(parsed, dict) else {"detail": raw}
    return {}


def log_detail_matches(entry: dict[str, Any], token: str) -> bool:
    """Match operator_log detail whether stored as plain text or JSON envelope."""
    raw = entry.get("detail")
    if raw is None:
        return False
    if isinstance(raw, dict):
        return token in str(raw.get("detail", "")) or token in json.dumps(raw)
    if isinstance(raw, str):
        if token in raw:
            return True
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return token == raw
        if isinstance(parsed, dict):
            return token in str(parsed.get("detail", "")) or token in json.dumps(parsed)
        return token == raw
    return token == str(raw)


def minimal_preclean_lineage(**patch: Any) -> dict[str, Any]:
    doc = {
        "provider": "deepfilternet",
        "scope": "full_source",
        "source_path": "ASSETS/input/interview.wav",
        "source_sha256": "0" * 64,
        "output_path": "preclean/isolated.wav",
        "isolated_sha256": "1" * 64,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    doc.update(patch)
    return doc


def minimal_preclean_provider(**patch: Any) -> dict[str, Any]:
    doc = {
        "provider": "deepfilternet",
        "scope": "full_source",
        "model": "DeepFilterNet3",
    }
    doc.update(patch)
    return doc


def minimal_coherence_report(**patch: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": 1,
        "derived_from": {
            "computed_at": "2026-01-01T00:00:00+00:00",
            "phase": "post_content_context",
            "duration_ms": 1_800_000,
        },
        "gate": {"min_duration_ms": 1_200_000, "activated": True, "duration_ms": 1_800_000},
        "scores": [],
        "risks": [
            {
                "risk_id": "r1",
                "kind": "topic_drift",
                "time_ms": 60_000,
                "confidence": 0.8,
                "evidence": {},
                "status": "open",
            }
        ],
        "summary": {
            "topic_drift_count": 1,
            "claim_contradiction_count": 0,
            "missing_callback_count": 0,
        },
    }
    doc.update(patch)
    return doc


def copy_shipped_config(dest_parent: Path) -> Path:
    """Copy ``config/`` into a fake repo root, minus per-machine overrides.

    Tests that build a throwaway repo (copytree config + INTERVIEW_MUX_ROOT) want
    the *shipped* configuration. Copying the tree wholesale also drags in the
    gitignored ``config/app.local.json``, and any absolute path in it (an
    executions_root moved off the repo volume, local runtime venvs) then resolves
    outside the sandbox, so the fixture's seeded runs become invisible. Excluding
    the overlay keeps these tests independent of whatever the operator has
    configured locally.
    """
    import shutil

    from interview_mux.config import repo_root as _real_repo_root

    dest = Path(dest_parent) / "config"
    shutil.copytree(
        _real_repo_root() / "config",
        dest,
        ignore=shutil.ignore_patterns("app.local.json"),
    )
    return dest

def patch_merged_config(monkeypatch, cfg: dict[str, Any]) -> None:
    """Patch merged_config in every imported module that binds it at load time.

    Pre-import all targets *before* patching ``interview_mux.config`` so modules
    that ``from interview_mux.config import merged_config`` bind the real
    function. Otherwise monkeypatch undoes to the fake and leaks absolute
    ``assets_root`` across tests (homunculus create-run failures).
    """
    import importlib

    mods: list[Any] = []
    seen: set[str] = set()
    for mod_name in _MERGED_CONFIG_MODULES:
        if mod_name in seen:
            continue
        seen.add(mod_name)
        try:
            mods.append(importlib.import_module(mod_name))
        except ImportError:
            continue

    def _fake_merged_config(_cfg: dict[str, Any] = cfg) -> dict[str, Any]:
        return _cfg

    for mod in mods:
        if hasattr(mod, "merged_config"):
            monkeypatch.setattr(mod, "merged_config", _fake_merged_config)


def patch_write_approval_enabled(monkeypatch, *, enabled: bool = True) -> None:
    """Force legacy write-approval staging (v2 auto-commit disables it by default)."""
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: enabled,
    )
    monkeypatch.setattr(
        "interview_mux.v2.config.v2_auto_commit",
        lambda: not enabled,
    )

def _execution_number_from_run_id(run_id: str) -> int | None:
    if not run_id.startswith("exec_"):
        return None
    part = run_id.split("_")[1]
    return int(part) if part.isdigit() else None

def ensure_test_wav(
    root: Path,
    rel: str = "ASSETS/input/interview.wav",
    *,
    content: bytes = MINIMAL_WAV_BYTES,
) -> Path:
    """Create a minimal WAV under root for init_run_meta / hash tests."""
    wav = root / rel
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(content)
    return wav

def populated_analysis_state(run_id: str, *, verified: bool = False) -> dict[str, Any]:
    """Minimal complete analysis_state for gate / handoff tests."""
    from interview_mux.analysis_memory import default_analysis_state

    state = default_analysis_state(run_id)
    state["themes"] = [{"id": "t1", "label": "Theme", "summary": "Summary text"}]
    state["narrative"] = {"thesis": "Core thesis from the interview."}
    state["interview_identity"] = {"one_line_summary": "A conversation about testing."}
    state["style"] = {
        "tone": "Warm investigative conversation",
        "tone_class": "journalistic",
        "format_class": "one_on_one",
        "pacing": "measured",
        "format_notes": "",
        "interviewer_style": "curious",
        "interviewee_style": "analytical",
    }
    state["meta"]["operator_verified"] = verified
    state["completion"] = {"analysis_ready": True, "blockers": []}
    return state

def init_run_meta_for_test(
    ctx: RunContext,
    input_audio_path: str = "ASSETS/input/demo.wav",
    *,
    source_audio_hash: str | None = TEST_SOURCE_AUDIO_HASH,
    source_audio_hash_short: str | None = TEST_SOURCE_AUDIO_HASH_SHORT,
) -> None:
    """Minimal run_meta when run_dir is outside the repo tree (pytest tmp_path)."""
    now = datetime.now(timezone.utc).isoformat()
    meta: dict[str, Any] = {
        "created_at": now,
        "updated_at": now,
        "execution_id": ctx.run_id,
        "execution_number": _execution_number_from_run_id(ctx.run_id),
        "input_audio_path": input_audio_path,
        "storage_root": str(ctx.run_dir.relative_to(ctx.root)) if ctx.run_dir.is_relative_to(ctx.root) else str(ctx.run_dir),
    }
    if source_audio_hash:
        meta["source_audio_hash"] = source_audio_hash
    if source_audio_hash_short:
        meta["source_audio_hash_short"] = source_audio_hash_short
    write_fixture_json(ctx, "run_meta.json", meta)

def isolated_run_ctx(tmp_path: Path, run_id: str) -> RunContext:
    """Run under tmp_path only — avoids collisions with data/run_* in the repo."""
    ctx = RunContext(run_id, create=False)
    ctx.run_dir = tmp_path / run_id
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done").mkdir(exist_ok=True)
    (ctx.run_dir / "vo_pickup").mkdir(exist_ok=True)
    return ctx

def ctx_from_fixture(tmp_path: Path, *, run_id: str = "exec_smoke_fixture") -> RunContext:
    """Copy tests/fixtures/runs/base_smoke into tmp_path for pipeline/gate smokes."""
    fixture = Path(__file__).parent / "fixtures" / "runs" / "base_smoke"
    run_dir = tmp_path / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(fixture, run_dir)
    ctx = RunContext(run_id, create=False)
    ctx.run_dir = run_dir
    return ctx

def minimal_source_acoustic_profile(**patch: Any) -> dict[str, Any]:
    """Schema-valid SAP for tests that write via RunContext.write_json."""
    base: dict[str, Any] = {
        "schema_version": 1,
        "derived_from": {
            "normalized_wav": "ingest/normalized.wav",
            "transcript": "transcript/full.json",
            "computed_at": "2026-01-01T00:00:00+00:00",
            "stage": "source_acoustic_profile",
        },
        "pacing": {
            "global_wpm": 142,
            "wpm_by_quartile": [130, 140, 145, 150],
            "pause_p50_ms": 680,
            "pace_class": "conversational",
        },
        "energy": {"room_timbre_hint": "dry_close_mic_warm_low_mid"},
        "mix_contract": {"underscore_policy": "normal", "duck_under_speech_db": 16},
        "prompt_tokens": {
            "bed": "loopable ambient bed, no melody hook",
            "stinger": "soft mid-register rise under 1.5s",
            "avoid": "trailer whoosh, drum loop",
            "density": "normal beds; pace=conversational",
        },
        "placement_hints": {
            "stinger_density": "low",
            "prefer_stinger_after_pause_tail": True,
            "stinger_min_pause_after_speech_ms": 400,
        },
        "operator_overrides": {},
    }
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base

def sound_design_plan_with(**patch: Any) -> dict[str, Any]:
    """Schema-valid sound_design_plan.json starting from defaults."""
    from interview_mux.analysis_memory import default_sound_design_plan

    plan = default_sound_design_plan()
    for key, value in patch.items():
        if key == "flow_plans" and isinstance(value, dict):
            flow_plans = dict(plan.get("flow_plans") or {})
            for flow_key, flow_val in value.items():
                if isinstance(flow_val, dict) and isinstance(flow_plans.get(flow_key), dict):
                    flow_plans[flow_key] = {**flow_plans[flow_key], **flow_val}
                else:
                    flow_plans[flow_key] = flow_val
            plan["flow_plans"] = flow_plans
        elif key == "assets" and isinstance(value, list):
            plan["assets"] = value
        elif key == "generated" and isinstance(value, dict):
            plan["generated"] = {**(plan.get("generated") or {}), **value}
        else:
            plan[key] = value
    return plan

def minimal_manifest_segment(
    segment_id: str = "seg_001",
    *,
    start_ms: int = 0,
    end_ms: int = 5000,
    text: str = "Sample segment text.",
    **patch: Any,
) -> dict[str, Any]:
    """Schema-valid segment for segments/manifest.json."""
    base: dict[str, Any] = {
        "segment_id": segment_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker_id": "spk_001",
        "speaker_role": "interviewer",
        "type": "interviewer_question",
        "text": text,
        "topic_tags": ["origin_story"],
    }
    base.update(patch)
    return base

def minimal_manifest(*segments: dict[str, Any] | str) -> dict[str, Any]:
    """Schema-valid segments/manifest.json payload."""
    if not segments:
        return {"segments": [minimal_manifest_segment()]}
    out: list[dict[str, Any]] = []
    for i, seg in enumerate(segments):
        if isinstance(seg, str):
            out.append(minimal_manifest_segment(seg, start_ms=i * 5000, end_ms=(i + 1) * 5000))
        else:
            out.append(seg)
    return {"segments": out}

def minimal_narrative_plan(**patch: Any) -> dict[str, Any]:
    """Schema-valid master/narrative_plan.json."""
    base: dict[str, Any] = {
        "arc_summary": "Test narrative arc for pytest.",
        "chapters": [
            {
                "chapter_id": "ch_01",
                "title": "Opening",
                "suggested_open_segment_id": "seg_001",
            }
        ],
        "ordering_constraints": [],
    }
    for key, value in patch.items():
        base[key] = value
    return base

def minimal_gap_line(**patch: Any) -> dict[str, Any]:
    """Schema-valid gap_report interviewer line."""
    base: dict[str, Any] = {
        "line_id": "line_001",
        "targets_segment_id": "seg_001",
        "delivery": "record",
        "gap_type": "missing_setup",
        "text": "Can you add context here?",
        "placement": "before",
    }
    base.update(patch)
    return base

def minimal_gap_report(*lines: dict[str, Any]) -> dict[str, Any]:
    """Schema-valid understanding/gap_report.json."""
    if not lines:
        return {"interviewer_lines": []}
    return {"interviewer_lines": list(lines)}


def seed_complete_gap_report(*lines: dict[str, Any]) -> dict[str, Any]:
    """Gap report that does not demand an audible opening-orientation seat."""
    doc = minimal_gap_report(*lines)
    doc["opening_orientation"] = {"omitted": True, "required": False}
    return doc

def minimal_gap_evaluations(*evaluations: dict[str, Any]) -> dict[str, Any]:
    """Schema-valid understanding/gap_evaluations.json."""
    if not evaluations:
        evaluations = (
            {
                "segment_id": "seg_001",
                "self_explanatory": True,
                "gap_type": "ok_with_light_bridge",
                "listener_confusion": "",
                "severity": "low",
            },
        )
    return {"evaluations": list(evaluations)}

def minimal_speakers() -> dict[str, Any]:
    return {
        "speakers": [
            {
                "speaker_id": "spk_0",
                "role": "interviewer",
                "confidence": 0.95,
                "evidence": ["Opening question pattern"],
            },
            {
                "speaker_id": "spk_1",
                "role": "interviewee",
                "confidence": 0.92,
                "evidence": ["Extended answers"],
            },
        ]
    }

def minimal_master_selection(**patch: Any) -> dict[str, Any]:
    """Schema-valid master/selection.json with sanitary order-lock + sanitize stamp."""
    from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta
    from interview_mux.order_hash import bump_order_lock

    base: dict[str, Any] = {
        "ordered_segment_ids": ["seg_001"],
        "chapters": [
            {
                "chapter_id": "ch_01",
                "title": "Opening",
                "segment_ids": ["seg_001"],
            }
        ],
    }
    base.update(patch)
    base = bump_order_lock(base, source="run_fixtures.minimal_master_selection")
    return stamp_sanitize_meta(
        base,
        ok=True,
        source="run_fixtures.minimal_master_selection",
        content_keys=["ordered_segment_ids", "order_content_hash"],
    )


def seed_flow1_full_sound_path(ctx: RunContext) -> None:
    """Flow 1 sound path with ranking, transitions, and narrative plan stubs for cross-validate."""
    seed_flow1_sound_spend_ready(ctx)
    write_fixture_json(ctx, "master/selection.json", minimal_master_selection())
    write_fixture_json(
        ctx,
        "master/transitions.json",
        {
            "transitions": [
                {
                    "transition_id": "t1",
                    "type": "topic_shift",
                    "before_segment_id": "seg_001",
                    "after_segment_id": "seg_001",
                    "text": "Next.",
                }
            ]
        },
    )
    write_fixture_json(
        ctx,
        "master/narrative_plan.json",
        minimal_narrative_plan(),
        stage_key="narrative_arc_plan",
    )

def seed_flow1_sound_spend_ready(ctx: RunContext) -> None:
    """Minimal Flow 1 sound path artifacts for cross-validate spend/mix regression tests."""
    seed_analysis_ready_artifacts(ctx, verified=True)
    if not ctx.artifact_exists("run_meta.json"):
        init_run_meta_for_test(ctx)
    write_fixture_json(
        ctx,
        "master/selection.json",
        minimal_master_selection(chapters=[]),
    )
    # Creative / music-only delivery needs role-diverse theme assets + a bed cue.
    assets = [
        {
            "asset_id": "theme_underscore_01",
            "role": "theme_underscore",
            "palette_id": "p1",
            "description": "Warm sparse underscore bed",
            "duration_seconds": 14.0,
        },
        {
            "asset_id": "theme_cold_open_01",
            "role": "theme_cold_open",
            "palette_id": "p1",
            "description": "Show open theme motif",
            "duration_seconds": 12.0,
        },
        {
            "asset_id": "theme_outro_01",
            "role": "theme_outro",
            "palette_id": "p1",
            "description": "Episode close theme",
            "duration_seconds": 12.0,
        },
        {
            "asset_id": "theme_emphasis_01",
            "role": "theme_emphasis",
            "palette_id": "p1",
            "description": "Chapter emphasis sting",
            "duration_seconds": 8.0,
        },
    ]
    plan = sound_design_plan_with(
        coherence={
            "sonic_identity": "warm dry close-mic room",
            "primary_mood": "intimate",
            "density": "sparse",
        },
        assets=assets,
        flow_plans={
            "podcast": {
                "cues": [
                    {
                        "cue_id": "c1",
                        "asset_id": "theme_underscore_01",
                        "role": "theme_underscore",
                        "placement": "under_segment",
                        "segment_id": "seg_001",
                    }
                ]
            }
        },
    )
    plan["_meta"] = {"producer_stage": "sound_design_plan"}
    write_fixture_json(ctx, "understanding/sound_design_plan.json", plan)
    write_fixture_json(
        ctx,
        "sound_design/sfx_prompts.json",
        {
            "prompts": [
                {
                    "asset_id": a["asset_id"],
                    "sfx_prompt": (
                        f"instrumental non-vocal music for podcast {a['role']} "
                        "without lyrics speech or foley"
                    ),
                    "duration_seconds": int(a["duration_seconds"]),
                    "negative_prompt": "vocals lyrics speech whoosh foley",
                    "role": a["role"],
                }
                for a in assets
            ]
        },
    )
    for aid in (
        "theme_underscore_01",
        "theme_cold_open_01",
        "theme_outro_01",
        "theme_emphasis_01",
    ):
        write_fixture_theme_wav(ctx, f"sound_design/assets/{aid}.wav")

def seed_from_sonic_fixture(
    ctx: RunContext,
    fixture_name: str,
    *,
    seed_base: bool = True,
) -> dict[str, Any]:
    """Load tests/fixtures/sonic_context/{fixture_name}.json into the run."""
    fixture_path = Path(__file__).parent / "fixtures" / "sonic_context" / f"{fixture_name}.json"
    if not fixture_path.is_file():
        raise FileNotFoundError(f"Missing sonic fixture: {fixture_path}")
    doc = json.loads(fixture_path.read_text(encoding="utf-8"))
    if seed_base:
        ctx.path("understanding").mkdir(parents=True, exist_ok=True)
        if not ctx.artifact_exists("understanding/content_brief.json"):
            write_fixture_json(ctx, "understanding/content_brief.json", minimal_content_brief())
        if not ctx.artifact_exists("segments/manifest.json"):
            write_fixture_json(ctx, "segments/manifest.json", minimal_manifest())
    write_fixture_json(ctx, "understanding/sonic_context.json", doc)
    return doc

def seed_analysis_ready_artifacts(ctx: RunContext, *, verified: bool = False) -> None:
    """Write minimal complete analysis artifacts for gate / hardening tests."""
    from interview_mux.artifact_writes import write_validated_artifact

    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.path("segments").mkdir(parents=True, exist_ok=True)
    write_validated_artifact(
        ctx,
        "understanding/speakers.json",
        minimal_speakers(),
        merge_from_disk=False,
        stage_key="speaker_roles",
    )
    write_validated_artifact(
        ctx,
        "understanding/content_brief.json",
        minimal_content_brief(),
        merge_from_disk=False,
        stage_key="content_brief_reanchor",
    )
    write_validated_artifact(
        ctx,
        "segments/manifest.json",
        minimal_manifest(),
        merge_from_disk=False,
        stage_key="segment_classification",
    )
    write_validated_artifact(
        ctx,
        "understanding/gap_evaluations.json",
        minimal_gap_evaluations(),
        merge_from_disk=False,
        stage_key="missing_framing",
    )
    write_validated_artifact(
        ctx,
        "understanding/gap_report.json",
        minimal_gap_report(),
        merge_from_disk=False,
        stage_key="gap_framing_compose",
    )
    brief = {
        "version": 1,
        "source_duration_ms": 60_000,
        # Keep min at/under the default 5s fixture segment so post_ranking duration
        # gates do not fail hollow sound-path seeds.
        "target_duration_sec": {"min": 5, "ideal": 45, "max": 60},
        "question_budget": {"min": 0, "ideal": 1, "max": 2},
        "chapter_budget": {"min": 1, "ideal": 2, "max": 4},
        "selection_mode": "coverage_first",
        "sfx_density": {"max_beds": 1, "max_punctuators": 1, "max_foley": 0},
        "ranking_weights": {},
        "rationale": ["fixture"],
        "operator_overrides": {},
        "generated": {"at": "1970-01-01T00:00:00+00:00", "by": "test_fixture"},
    }
    write_validated_artifact(
        ctx,
        "understanding/delivery_brief.json",
        brief,
        merge_from_disk=False,
        stage_key="delivery_brief_build",
    )
    state = populated_analysis_state(ctx.run_id, verified=verified)
    state["completion"] = {"analysis_ready": True, "blockers": []}
    write_validated_artifact(
        ctx,
        "understanding/analysis_state.json",
        state,
        merge_from_disk=False,
        stage_key="content_context",
    )
    prev = getattr(ctx, "_mark_done_raw", False)
    ctx._mark_done_raw = True
    try:
        ctx.mark_done("optimal_questions")
    finally:
        ctx._mark_done_raw = prev

def minimal_flow2_selection(**patch: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "reel_thesis": "Highlight reel thesis for pytest.",
        "highlights": [
            {
                "rank": 1,
                "segment_id": "seg_001",
                "start_ms": 0,
                "end_ms": 5000,
                "headline": "Hook",
                "scores": {
                    "salience": 0.9,
                    "clarity": 0.8,
                    "emotion": 0.7,
                    "quotability": 0.6,
                    "diversity_bonus": 0.1,
                },
            }
        ],
    }
    for key, value in patch.items():
        base[key] = value
    return base

def minimal_content_brief(**patch: Any) -> dict[str, Any]:
    """Schema-valid understanding/content_brief.json."""
    base: dict[str, Any] = {
        "thesis": "Test thesis for pytest.",
        "topics": [{"name": "Topic A", "summary": "Summary here."}],
        "topic_relationships": [
            {
                "from_topic": "Topic A",
                "to_topic": "Topic B",
                "relation": "supports",
            }
        ],
        "jargon_glossary": [
            {
                "term": "ICP",
                "plain_definition": "Ideal customer profile",
                "first_segment_id": None,
            }
        ],
        "emotional_beats": [
            {
                "label": "tension",
                "description": "Early uncertainty",
                "segment_ids": [],
            }
        ],
    }
    base.update(patch)
    return base

def patch_server_ctx(monkeypatch, ctx: RunContext) -> None:
    """Route FastAPI handlers to an isolated RunContext."""
    from fastapi import HTTPException

    from interview_mux.web import server

    def _ctx(run_id: str) -> RunContext:
        if run_id != ctx.run_id:
            raise HTTPException(404, f"Run not found: {run_id}")
        return ctx

    monkeypatch.setattr(server, "_ctx", _ctx)

def patch_executions_root(monkeypatch, tmp_path: Path, **cfg_overrides: Any) -> Path:
    """Point executions_root at tmp_path so JobRunner threads resolve the same run dir."""
    from interview_mux.config import merged_config

    root = tmp_path / "ASSETS" / "executions"
    root.mkdir(parents=True, exist_ok=True)
    cfg = {
        **merged_config(),
        "assets_root": str((tmp_path / "ASSETS").resolve()),
        "executions_root": str(root.resolve()),
        **cfg_overrides,
    }
    patch_merged_config(monkeypatch, cfg)
    return root

def seed_analysis_complete(ctx: RunContext) -> None:
    """Mark shared analysis done and satisfy G0/G1 gates for flow execution."""
    from interview_mux import pipeline
    from interview_mux.analysis_memory import default_analysis_state

    for stage in pipeline.ANALYSIS_ORDER:
        mark_done_raw(ctx, stage)
    mark_done_raw(ctx, "transcript_review", "vo_ingest")
    state = default_analysis_state(ctx.run_id)
    state["meta"]["operator_verified"] = True
    write_fixture_json(ctx, "understanding/analysis_state.json", state)
    write_fixture_json(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "line_001",
                    "targets_segment_id": "seg_001",
                    "delivery": "record",
                    "gap_type": "context",
                    "text": "Add context",
                    "placement": "before",
                }
            ]
        },
    )
    pickup = ctx.final_path("vo_pickup")
    write_fixture_vo_wav(pickup / "line_001.wav")
    confirm_test_pickup_speaker(ctx)
    write_fixture_json(ctx, "analysis_complete.json", {"analysis_ready": True, "blockers": []})
    if ctx.artifact_exists("run_meta.json"):
        meta = ctx.read_json("run_meta.json")
    else:
        meta = {}
    meta["handoff_ack"] = {
        "sound_design_palettes": "2026-01-01T00:00:00+00:00",
        "speaker_roles": "2026-01-01T00:00:00+00:00",
        "content_context": "2026-01-01T00:00:00+00:00",
    }
    meta["handoff_pending_writes"] = {}
    write_fixture_json(ctx, "run_meta.json", meta)
