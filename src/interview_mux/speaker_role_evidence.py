"""Deterministic speaker role hints from diarized transcript samples."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# After G0, diarization is locked inside transcribe — there is no standalone
# speaker_diarization stage to re-run. Blocking rerun_stage needs for these
# names are unfulfillable and must not dead-end speaker_roles.
UNFULFILLABLE_DIARIZATION_STAGES = frozenset(
    {
        "diarization",
        "speaker_diarization",
        "transcribe",
        "audio_preclean",
    }
)

_QUESTION_RE = re.compile(r"\?\s*$")
_INTERVIEWER_CUES = (
    "tell me",
    "can you",
    "what was",
    "how did",
    "why did",
    "walk me through",
    "describe",
)


def _sample_lines(samples: Any) -> list[tuple[str | None, str]]:
    lines: list[tuple[str | None, str]] = []
    if isinstance(samples, str):
        for raw in samples.splitlines():
            text = raw.strip()
            if text:
                lines.append((None, text))
        return lines
    if isinstance(samples, list):
        for item in samples:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    lines.append((None, text))
            elif isinstance(item, dict):
                speaker = str(item.get("speaker_id") or item.get("speaker") or "") or None
                text = str(item.get("text") or item.get("content") or "").strip()
                if text:
                    lines.append((speaker, text))
    return lines


def build_speaker_role_evidence(stage_input: dict[str, Any]) -> dict[str, Any]:
    """
    Extract lightweight Q&A / turn-taking hints to help speaker_roles LLM passes.
    Does not assign roles — only surfaces observable patterns.
    """
    speakers_raw = stage_input.get("speakers")
    speaker_ids: list[str] = []
    if isinstance(speakers_raw, dict):
        for row in speakers_raw.get("speakers") or speakers_raw.get("items") or []:
            if isinstance(row, dict) and row.get("speaker_id"):
                speaker_ids.append(str(row["speaker_id"]))
    elif isinstance(speakers_raw, list):
        for row in speakers_raw:
            if isinstance(row, dict) and row.get("speaker_id"):
                speaker_ids.append(str(row["speaker_id"]))

    lines = _sample_lines(stage_input.get("transcript_samples"))
    question_turns: list[dict[str, Any]] = []
    turn_counts: dict[str, int] = {}
    for speaker, text in lines:
        sid = speaker or "unknown"
        turn_counts[sid] = turn_counts.get(sid, 0) + 1
        lower = text.lower()
        is_question = bool(_QUESTION_RE.search(text)) or any(cue in lower for cue in _INTERVIEWER_CUES)
        if is_question:
            question_turns.append({"speaker_id": speaker, "text_excerpt": text[:160]})

    hints: list[str] = []
    if question_turns:
        q_speakers = {str(q.get("speaker_id")) for q in question_turns if q.get("speaker_id")}
        if len(q_speakers) == 1:
            hints.append(
                f"Speaker {next(iter(q_speakers))} asks most interview-style questions — likely interviewer."
            )
        elif len(q_speakers) > 1:
            hints.append(f"Multiple speakers ask questions: {', '.join(sorted(q_speakers))}.")
    if speaker_ids and turn_counts:
        ranked = sorted(turn_counts.items(), key=lambda x: x[1], reverse=True)
        if len(ranked) >= 2 and ranked[0][1] > ranked[1][1] * 1.5:
            hints.append(
                f"Speaker {ranked[0][0]} has the highest talk time in samples ({ranked[0][1]} turns)."
            )

    pair_verdicts = _pair_verdicts(stage_input.get("diarization_repairs"))
    if pair_verdicts:
        same = [p for p in pair_verdicts if p.get("same_speaker") is True]
        different = [p for p in pair_verdicts if p.get("same_speaker") is False]
        if same:
            hints.append(
                f"{len(same)} Sortformer pair(s) judged the same speaker across a flip seam."
            )
        if different:
            hints.append(
                f"{len(different)} Sortformer pair(s) judged different speakers across a flip seam."
            )

    return {
        "role_evidence_hints": hints,
        "question_turns": question_turns[:12],
        "sample_turn_counts": turn_counts,
        "diarized_speaker_ids": speaker_ids,
        "diarization_pair_verdicts": pair_verdicts,
    }


def enrich_content_brief_from_evidence(ctx: Any) -> bool:
    """Populate guest_name/host_name on content_brief when speakers lack display names."""
    if not getattr(ctx, "artifact_exists", lambda _p: False)("understanding/content_brief.json"):
        return False
    try:
        brief = ctx.read_json("understanding/content_brief.json")
    except Exception:
        return False
    if not isinstance(brief, dict):
        return False
    changed = False
    guest = str(brief.get("guest_name") or "").strip()
    host = str(brief.get("host_name") or "").strip()
    if guest and host:
        return False
    roles: list[dict[str, Any]] = []
    if getattr(ctx, "artifact_exists", lambda _p: False)("understanding/speakers.json"):
        try:
            sp = ctx.read_json("understanding/speakers.json")
            roles = [
                r
                for r in ((sp or {}).get("speakers") or [])
                if isinstance(r, dict)
            ]
        except Exception:
            roles = []
    for row in roles:
        role = str(row.get("role") or row.get("speaker_role") or "").lower()
        name = str(
            row.get("display_name")
            or row.get("canonical_name")
            or row.get("name")
            or row.get("label")
            or ""
        ).strip()
        if not name:
            continue
        if "interviewee" in role or "guest" in role:
            if not guest:
                brief["guest_name"] = name
                guest = name
                changed = True
        if "interviewer" in role or "host" in role:
            if not host:
                brief["host_name"] = name
                host = name
                changed = True
    if not guest:
        try:
            meta = ctx.read_json("run_meta.json") if getattr(ctx, "artifact_exists", lambda _p: False)(
                "run_meta.json"
            ) else {}
            src = str((meta or {}).get("source_audio") or (meta or {}).get("input_audio") or "")
            stem = Path(src).stem.replace("_", " ").replace("-", " ")
            tokens = [t for t in stem.split() if t and t[0].isupper()]
            if len(tokens) >= 2:
                brief["guest_name"] = tokens[0]
                changed = True
        except Exception:
            pass
    if changed:
        ctx.write_json("understanding/content_brief.json", brief)
    return changed


def is_unfulfillable_diarization_need(need: Any) -> bool:
    """True when an LLM need asks to re-run locked / non-existent diarization."""
    if not isinstance(need, dict):
        return False
    ntype = str(need.get("type") or "").strip().lower()
    if ntype != "rerun_stage":
        return False
    stage = str(need.get("stage") or "").strip().lower()
    if not stage:
        return False
    if stage in UNFULFILLABLE_DIARIZATION_STAGES:
        return True
    return "diarization" in stage


def _question_score(row: dict[str, Any]) -> float:
    talk_ms = max(1.0, float(row.get("talk_ms") or 1.0))
    questions = float(row.get("question_count") or 0)
    return questions + (questions / talk_ms) * 1000.0


def dominant_roles_from_talk_stats(talk_stats: Any) -> list[dict[str, Any]]:
    """Assign interviewer/interviewee from talk time + questions.

    Longest talker is the guest unless they are the only question-asker.
    Never assign interviewer to the longest speaker when another ID asked
    interview-style questions (matches speaker-roles prompt).
    """
    rows = [
        r
        for r in (talk_stats or [])
        if isinstance(r, dict) and str(r.get("speaker_id") or "").strip()
    ]
    if not rows:
        return []
    ranked = sorted(rows, key=lambda r: float(r.get("talk_ms") or 0.0), reverse=True)
    guest = ranked[0]
    others = ranked[1:]
    host: dict[str, Any] | None = None
    if others:
        host = max(others, key=_question_score)
        guest_qs = float(guest.get("question_count") or 0)
        host_qs = float(host.get("question_count") or 0)
        # If the long speaker asked everything and others asked none, keep
        # the shorter speaker as interviewer (frame) anyway — typical bleed.
        if host_qs == 0 and guest_qs == 0:
            host = others[0]
    guest_id = str(guest.get("speaker_id"))
    host_id = str(host.get("speaker_id")) if host else ""
    out: list[dict[str, Any]] = []
    for row in ranked:
        sid = str(row.get("speaker_id"))
        qs = int(row.get("question_count") or 0)
        if sid == host_id:
            role, narrative, density = "interviewer", "frame", "high" if qs >= 3 else "medium"
        elif sid == guest_id:
            role, narrative, density = "interviewee", "storyteller", "low"
        else:
            role, narrative, density = "panelist", "analytical_lens", "low"
        out.append(
            {
                "speaker_id": sid,
                "role": role,
                "narrative_function": narrative,
                "confidence": 0.62,
                "label": None,
                "evidence": [
                    (
                        f"dominant-role fallback: talk_ms={int(row.get('talk_ms') or 0)} "
                        f"questions={qs} turns={int(row.get('turn_count') or 0)}"
                    )
                ],
                "question_density": density,
                "avg_turn_length_ms": float(row.get("avg_turn_ms") or 0.0) or None,
            }
        )
    return out


def fallback_speakers_artifact(talk_stats: Any, *, notes: str = "") -> dict[str, Any] | None:
    """Legal speakers artifact when LLM refuses mixed-diarization IDs.

    Intentional Full-auto honesty path (SR-B2): after ≤2 OpenAI attempts, when
    the model asks for a locked diarization re-run, persist dominant roles from
    talk stats so the seed walk continues with a schema-valid primary instead of
    hollow stalling. Not a quality substitute for clean labels.
    """
    speakers = dominant_roles_from_talk_stats(talk_stats)
    if not speakers:
        return None
    n = len(speakers)
    format_class = "one_on_one" if n <= 2 else "panel"
    return {
        "speakers": speakers,
        "notes": notes
        or (
            "Diarization IDs are mixed after G0; assigned dominant roles from "
            "talk time and question counts. Diarization is locked — not re-run."
        ),
        "conversation_profile": {
            "format_class_candidate": format_class,
            "format_confidence": 0.58,
            "tone_class_candidate": "conversational",
            "dynamics": {
                "question_density": "medium",
                "turn_asymmetry": "high" if n <= 2 else "medium",
                "overlap_risk": "medium",
            },
        },
        "conversation_hypotheses": [
            {
                "id": "hyp_mixed_diarization_dominant",
                "format_class": format_class,
                "confidence": 0.58,
                "reason": "Speaker IDs contain bleed; roles are majority-signal, not clean labels.",
                "speaker_role_map": {s["speaker_id"]: s["role"] for s in speakers},
                "blocking": False,
            }
        ],
        "confirmed_conversation_hypothesis_id": None,
        "gap_sensitivity": {
            "format_class": format_class,
            "tone_class": "conversational",
            "severity_hints": {
                "missing_question": "strict" if format_class == "one_on_one" else "normal",
                "missing_setup": "strict",
                "missing_callback": "normal",
                "missing_definition": "strict" if format_class == "one_on_one" else "normal",
                "missing_followup": "normal",
                "ok_with_light_bridge": "strict",
            },
            "priority_gap_types": ["missing_question", "missing_setup"],
            "deemphasize_gap_types": [],
            "segment_focus": "interviewee_answer",
            "notes": "Dominant-role fallback after mixed diarization.",
        },
    }


def persist_mixed_diarization_fallback(ctx: Any, *, notes: str = "") -> list[str]:
    """Write understanding/speakers.json from talk stats and mark speaker_roles done."""
    from interview_mux.conversation_context import enrich_speakers_artifact
    from interview_mux.source_topology import _speaker_talk_stats

    if not ctx.artifact_exists("transcript/full.json"):
        return []
    transcript = ctx.read_json("transcript/full.json")
    speakers_doc = (
        ctx.read_json("transcript/speakers.json")
        if ctx.artifact_exists("transcript/speakers.json")
        else {"speakers": []}
    )
    if isinstance(speakers_doc, dict):
        speakers_input = {"speakers": speakers_doc.get("speakers") or speakers_doc}
    elif isinstance(speakers_doc, list):
        speakers_input = {"speakers": speakers_doc}
    else:
        speakers_input = {"speakers": []}
    stats = _speaker_talk_stats(transcript, speakers_input)
    artifact = fallback_speakers_artifact(stats, notes=notes)
    if not artifact:
        return []
    enriched = enrich_speakers_artifact(ctx, artifact)
    ctx.write_json("understanding/speakers.json", enriched, stage_key="speaker_roles")
    try:
        from interview_mux.analysis_memory import sync_speakers_to_state

        sync_speakers_to_state(ctx, enriched)
    except Exception:
        pass
    from interview_mux.delivery_guardrails import seed_stage_complete
    from interview_mux.stage_completion import heal_or_refuse_mark

    if not seed_stage_complete(ctx, "speaker_roles"):
        heal_or_refuse_mark(ctx, "speaker_roles", force=True)
    return ["understanding/speakers.json"]


def _pair_verdicts(repairs: Any) -> list[dict[str, Any]]:
    if not isinstance(repairs, dict):
        return []
    out: list[dict[str, Any]] = []
    for row in repairs.get("pairs") or []:
        if not isinstance(row, dict):
            continue
        verdict = str(row.get("verdict") or "").strip().lower()
        same: bool | None
        if verdict in {"yes_same", "yes"}:
            same = True
        elif verdict in {"no_different", "no"}:
            same = False
        else:
            same = None
        out.append(
            {
                "from_speaker_id": str(row.get("from_speaker_id") or ""),
                "to_speaker_id": str(row.get("to_speaker_id") or ""),
                "verdict": verdict,
                "same_speaker": same,
            }
        )
    return out[:40]


def _word_count(text: str) -> int:
    return len([w for w in str(text or "").split() if w])


def _is_guest_explanation(text: str) -> bool:
    if _word_count(text) < 40:
        return False
    if "?" in text:
        return False
    lower = text.lower()
    return not any(cue in lower for cue in _INTERVIEWER_CUES)


def _is_host_question(text: str) -> bool:
    if _word_count(text) > 25:
        return False
    lower = text.lower()
    return bool(_QUESTION_RE.search(text.strip())) or any(cue in lower for cue in _INTERVIEWER_CUES)


def lint_role_tape_conflicts(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Detect interviewer_question / interviewee_answer labels that contradict tape."""
    segs = (manifest or {}).get("segments") if isinstance(manifest, dict) else None
    if not isinstance(segs, list):
        return {"blocking": False, "conflict_count": 0, "typed_qa_count": 0, "examples": []}
    typed = 0
    conflicts: list[dict[str, Any]] = []
    for row in segs:
        if not isinstance(row, dict):
            continue
        stype = str(row.get("type") or "").strip()
        text = str(row.get("text") or "")
        if stype not in {"interviewer_question", "interviewee_answer"}:
            continue
        typed += 1
        sid = str(row.get("segment_id") or "")
        if stype == "interviewer_question" and _is_guest_explanation(text):
            conflicts.append(
                {
                    "segment_id": sid,
                    "type": stype,
                    "reason": "long_explanation_labeled_question",
                }
            )
        elif stype == "interviewee_answer" and _is_host_question(text):
            conflicts.append(
                {
                    "segment_id": sid,
                    "type": stype,
                    "reason": "short_question_labeled_answer",
                }
            )
    conflict_count = len(conflicts)
    ratio = (conflict_count / typed) if typed else 0.0
    blocking = conflict_count >= 4 and ratio >= 0.15
    return {
        "blocking": blocking,
        "conflict_count": conflict_count,
        "typed_qa_count": typed,
        "conflict_ratio": round(ratio, 4),
        "examples": conflicts[:8],
    }


def repair_role_tape_segment_types(ctx: Any) -> list[dict[str, Any]]:
    """Retype obvious QA label mismatches so missing_framing preflight can proceed."""
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    try:
        manifest = ctx.read_json("segments/manifest.json")
    except Exception:
        return []
    if not isinstance(manifest, dict):
        return []
    segs = manifest.get("segments")
    if not isinstance(segs, list):
        return []
    applied: list[dict[str, Any]] = []
    for row in segs:
        if not isinstance(row, dict):
            continue
        stype = str(row.get("type") or "").strip()
        text = str(row.get("text") or "")
        sid = str(row.get("segment_id") or "")
        if stype == "interviewer_question" and _is_guest_explanation(text):
            row["type"] = "interviewer_reaction"
            applied.append(
                {
                    "segment_id": sid,
                    "from": "interviewer_question",
                    "to": "interviewer_reaction",
                    "reason": "long_explanation_labeled_question",
                }
            )
        elif stype == "interviewee_answer" and _is_host_question(text):
            row["type"] = "interviewer_question"
            applied.append(
                {
                    "segment_id": sid,
                    "from": "interviewee_answer",
                    "to": "interviewer_question",
                    "reason": "short_question_labeled_answer",
                }
            )
    if not applied:
        return []
    try:
        from interview_mux.artifact_lifecycle import restamp_committed_artifact

        restamp_committed_artifact(
            ctx,
            "segments/manifest.json",
            producer_stage="segment_classification",
            doc=manifest,
        )
    except Exception:
        ctx.write_json("segments/manifest.json", manifest, stage_key="segment_classification")
    lint = lint_role_tape_conflicts(manifest)
    if not lint.get("blocking"):
        stamp_role_tape_conflict(ctx, lint)
        if ctx.artifact_exists("understanding/speakers.json"):
            try:
                spk = ctx.read_json("understanding/speakers.json")
                if isinstance(spk, dict):
                    spk.pop("role_tape_conflict", None)
                    ctx.write_json("understanding/speakers.json", spk, skip_handoff=True)
            except Exception:
                pass
    return applied


def stamp_role_tape_conflict(ctx: Any, lint: dict[str, Any]) -> None:
    if not ctx.artifact_exists("understanding/speakers.json"):
        return
    try:
        doc = ctx.read_json("understanding/speakers.json")
    except Exception:
        return
    if not isinstance(doc, dict):
        return
    doc["role_tape_conflict"] = lint
    ctx.write_json("understanding/speakers.json", doc, skip_handoff=True)
