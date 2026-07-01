"""Code-first artifact lint — runs before arbiter accept merge."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context

_GENERIC_THEMES = frozenset(
    {"leadership", "innovation", "success", "journey", "passion", "vision", "impact"}
)
_SPEECH_LYRICS_PATTERNS = (
    re.compile(r"\b(says|saying|spoken|narrator|voice over|lyrics?|verse|chorus)\b", re.I),
    re.compile(r'"[^"]{8,}"'),
)
_FORBIDDEN_MMAUDIO_STRINGS = (
    re.compile(r"elevenlabs", re.I),
    re.compile(r"music_v2", re.I),
    re.compile(r"/v1/", re.I),
    re.compile(r"POST\s+https?://", re.I),
)
_ROLE_DURATION_BANDS: dict[str, tuple[float, float]] = {
    "ambient_bed": (4.0, 8.0),
    "chapter_stinger": (1.0, 2.5),
    "transition_stinger": (1.0, 1.8),
    "cold_open": (1.5, 2.5),
    "vo_bridge": (1.0, 2.0),
    "accent_foley": (0.6, 1.5),
}
_DIEGETIC_HINTS = re.compile(r"\b(diegetic|street|traffic|crowd|cafe|restaurant|office chatter|sirens?)\b", re.I)


def _manifest_ids(ctx: RunContext) -> set[str]:
    """Segment ids for coverage denominator — prefer boundary contract."""
    if ctx.artifact_exists("segments/boundaries.json"):
        from interview_mux.stage_coupling import contract_segment_ids

        doc = ctx.read_json("segments/boundaries.json")
        if isinstance(doc, dict):
            ids = contract_segment_ids(doc)
            if ids:
                return set(ids)
    if not ctx.artifact_exists("segments/manifest.json"):
        return set()
    manifest = ctx.read_json("segments/manifest.json")
    segs = manifest.get("segments") or [] if isinstance(manifest, dict) else []
    return {str(s.get("segment_id")) for s in segs if isinstance(s, dict) and s.get("segment_id")}


def _artifacts(envelope: dict[str, Any]) -> dict[str, Any]:
    return envelope.get("artifacts") or {}


def _row_confidence_values(rows: Any) -> list[float]:
    out: list[float] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        conf = row.get("confidence")
        if isinstance(conf, (int, float)):
            out.append(float(conf))
    return out


def _artifact_row_confidences(stage_key: str, envelope: dict[str, Any]) -> list[float]:
    """Per-row confidence scores from stage artifacts (when present)."""
    artifacts = _artifacts(envelope)
    if stage_key == "speaker_roles":
        return _row_confidence_values(artifacts.get("speakers"))
    if stage_key in ("content_context", "content_brief_reanchor"):
        out = _row_confidence_values(artifacts.get("topics"))
        out.extend(_row_confidence_values(artifacts.get("key_claims")))
        return out
    return []


def reconcile_envelope_confidence(stage_key: str, envelope: dict[str, Any]) -> bool:
    """
    Align top-level envelope confidence with artifact row scores when the model
    reports a lower envelope value than its own per-row confidences.
    """
    row_conf = _artifact_row_confidences(stage_key, envelope)
    if not row_conf:
        return False
    derived = min(row_conf)
    current = float(envelope.get("confidence") or 0)
    if derived > current:
        envelope["confidence"] = derived
        return True
    return False


def _walk_segment_id_values(obj: Any, out: set[str]) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in (
                "segment_id",
                "after_segment_id",
                "before_segment_id",
                "targets_segment_id",
            ) and val:
                out.add(str(val))
            elif key == "ordered_segment_ids" and isinstance(val, list):
                out.update(str(x) for x in val if x)
            elif key == "segment_ids" and isinstance(val, list):
                out.update(str(x) for x in val if x)
            else:
                _walk_segment_id_values(val, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk_segment_id_values(item, out)


def collect_segment_ids_from_artifacts(stage_key: str, artifacts: dict[str, Any]) -> set[str]:
    """Collect segment id references from stage envelope artifacts."""
    refs: set[str] = set()
    if stage_key == "missing_framing":
        for row in artifacts.get("evaluations") or artifacts.get("gap_evaluations") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                refs.add(str(row["segment_id"]))
    elif stage_key == "segment_classification":
        for row in artifacts.get("segments") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                refs.add(str(row["segment_id"]))
    elif stage_key == "full_master_ranking":
        for sid in artifacts.get("ordered_segment_ids") or []:
            refs.add(str(sid))
    elif stage_key == "highlight_selection":
        for row in artifacts.get("clips") or artifacts.get("highlights") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                refs.add(str(row["segment_id"]))
    elif stage_key in ("topic_coverage_audit", "content_brief_reanchor"):
        for row in artifacts.get("topics") or []:
            if isinstance(row, dict):
                for sid in row.get("segment_ids") or []:
                    refs.add(str(sid))
    else:
        _walk_segment_id_values(artifacts, refs)
    return refs


def _reference_id_universe(ctx: RunContext, stage_key: str) -> set[str]:
    if stage_key in ("full_master_ranking", "edl_narrative_audit", "transitions"):
        if ctx.artifact_exists("flow_1_master/selection.json"):
            sel = ctx.read_json("flow_1_master/selection.json")
            return {str(x) for x in (sel.get("ordered_segment_ids") or [])}
        return set()
    return _manifest_ids(ctx)


def _coverage_numerator(stage_key: str, artifacts: dict[str, Any]) -> set[str]:
    return collect_segment_ids_from_artifacts(stage_key, artifacts)


def _transcript_duration_ms(ctx: RunContext) -> int:
    from interview_mux.interview_duration_policy import transcript_duration_ms

    return transcript_duration_ms(ctx)


def _has_topic_evidence(topic: dict[str, Any]) -> bool:
    if topic.get("approx_time_range"):
        return True
    seg_ids = topic.get("segment_ids")
    return isinstance(seg_ids, list) and bool(seg_ids)


def _claim_body(claim: dict[str, Any]) -> str:
    return str(claim.get("claim") or claim.get("text") or "").strip()


def _has_claim_evidence(claim: dict[str, Any]) -> bool:
    if claim.get("approx_time_range"):
        return True
    for key in ("evidence_segment_ids", "segment_ids"):
        ids = claim.get(key)
        if isinstance(ids, list) and ids:
            return True
    return False


def _content_context_long_interview_ms() -> int:
    from interview_mux.interview_duration_policy import content_context_long_interview_ms

    return content_context_long_interview_ms()


def _lint_speaker_roles(artifacts: dict[str, Any], _ctx: RunContext) -> list[str]:
    errors: list[str] = []
    speakers = artifacts.get("speakers") or []
    if not speakers:
        errors.append("speakers list empty")
        return errors
    roles = {str(s.get("role", "")).lower() for s in speakers if isinstance(s, dict)}
    interviewer_roles = {"interviewer", "moderator"}
    if not (roles & interviewer_roles):
        if all(
            isinstance(s, dict) and str(s.get("role", "")).lower() == "unknown"
            for s in speakers
        ):
            errors.append("all speakers unknown — Q&A may be evident")
    return errors


def _lint_content_context(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    if not str(artifacts.get("thesis", "")).strip():
        errors.append("thesis empty")
    long_interview = _transcript_duration_ms(ctx) >= _content_context_long_interview_ms()
    for topic in artifacts.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        name = str(topic.get("name", "")).strip().lower()
        if name in _GENERIC_THEMES and not _has_topic_evidence(topic):
            errors.append(f"generic theme without evidence: {name}")
        elif long_interview and name and not _has_topic_evidence(topic):
            errors.append(f"topic without evidence anchor: {name}")
    for claim in artifacts.get("key_claims") or []:
        if isinstance(claim, dict) and not _has_claim_evidence(claim):
            if _claim_body(claim):
                errors.append("key_claim without evidence anchor")
                break
    return errors


def _lint_boundary_detection(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    boundaries = artifacts.get("boundaries") or []
    if not boundaries:
        errors.append("no boundaries")
        return errors
    duration_ms = _transcript_duration_ms(ctx)
    from interview_mux.interview_duration_policy import boundary_micro_segment_min_ms

    if duration_ms > boundary_micro_segment_min_ms() and len(boundaries) > 200:
        errors.append("micro-segment explosion (>200 boundaries on long interview)")
    from interview_mux.interview_spine.config import spine_enabled
    from interview_mux.segment_timeline import validate_boundary_rows, segment_timeline_cfg

    st_cfg = segment_timeline_cfg()
    errors.extend(
        validate_boundary_rows(
            [b for b in boundaries if isinstance(b, dict)],
            require_speaker_id=bool(st_cfg.get("require_speaker_id", True)),
            allow_overlap_ms=int(st_cfg.get("allow_overlap_ms", 0)),
        )
    )
    if spine_enabled() and not ctx.artifact_exists("understanding/interview_spine.json"):
        errors.append("interview spine missing while interview_spine.enabled")
    return errors


def _lint_segment_classification(artifacts: dict[str, Any], _ctx: RunContext) -> list[str]:
    errors: list[str] = []
    segments = artifacts.get("segments") or []
    if not segments:
        errors.append("no classified segments")
    types = [str(s.get("type", "")) for s in segments if isinstance(s, dict)]
    if types and types.count("interviewee_answer") == len(types):
        errors.append("all segments typed interviewee_answer")
    return errors


def _lint_content_brief_reanchor(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    manifest_ids = _manifest_ids(ctx)
    for i, topic in enumerate(artifacts.get("topics") or []):
        if not isinstance(topic, dict):
            continue
        for seg_id in topic.get("segment_ids") or []:
            if manifest_ids and str(seg_id) not in manifest_ids:
                errors.append(f"topics[{i}] segment_id {seg_id} not in manifest")
    return errors


def _lint_missing_framing(artifacts: dict[str, Any], _ctx: RunContext) -> list[str]:
    evaluations = artifacts.get("evaluations") or artifacts.get("gap_evaluations") or []
    if not evaluations:
        return ["no gap evaluations"]
    return []


def _lint_sound_design_palettes(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    coherence = artifacts.get("coherence") or {}
    if not str(coherence.get("sonic_identity", "")).strip():
        errors.append("coherence.sonic_identity empty")
    manifest_ids = _manifest_ids(ctx)
    palettes = artifacts.get("palettes") or []
    if not palettes:
        errors.append("no palettes")
    for p in palettes:
        if not isinstance(p, dict):
            continue
        keywords = [str(k).strip().lower() for k in (p.get("keywords") or []) if str(k).strip()]
        if keywords:
            overlap = set(keywords) & _sonic_tag_keywords(ctx)
            if not overlap:
                errors.append(f"palette {p.get('palette_id')} keywords lack sonic_context provenance")
        seg_ids = p.get("segment_ids") or []
        if not seg_ids:
            errors.append(f"palette {p.get('palette_id')} has no segment_ids")
        elif manifest_ids:
            for sid in seg_ids:
                if str(sid) not in manifest_ids:
                    errors.append(f"palette segment_id {sid} not in manifest")
                    break
    return errors


def _lint_sound_design_plan_flow1(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    cfg = merged_config()
    cap = int((cfg.get("sound_design") or {}).get("max_assets_flow1", 6))
    assets = artifacts.get("assets") or []
    asset_ids = {str(a.get("asset_id")) for a in assets if isinstance(a, dict) and a.get("asset_id")}
    if len(asset_ids) > cap:
        errors.append(f"asset count {len(asset_ids)} exceeds cap {cap}")
    cues = ((artifacts.get("flow_plans") or {}).get("flow1") or {}).get("cues") or []
    selection_ids: set[str] = set()
    if ctx.artifact_exists("flow_1_master/selection.json"):
        sel = ctx.read_json("flow_1_master/selection.json")
        selection_ids = set(sel.get("ordered_segment_ids") or [])
    palette_seg_ids: set[str] = set()
    sdp = ctx.read_json("understanding/sound_design_plan.json") if ctx.artifact_exists(
        "understanding/sound_design_plan.json"
    ) else {}
    for pal in (sdp.get("palettes") or artifacts.get("palettes") or []):
        if isinstance(pal, dict):
            palette_seg_ids.update(str(x) for x in (pal.get("segment_ids") or []))
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        aid = str(cue.get("asset_id", ""))
        if aid and aid not in asset_ids:
            errors.append(f"cue {cue.get('cue_id')} references unknown asset_id {aid}")
        for key in ("segment_id", "after_segment_id", "before_segment_id"):
            sid = cue.get(key)
            if sid and selection_ids and str(sid) not in selection_ids:
                errors.append(f"cue anchor {key}={sid} not in selection")
        if cue.get("placement") == "under_segment" and palette_seg_ids:
            seg = cue.get("segment_id")
            if seg and str(seg) not in palette_seg_ids:
                errors.append(f"bed cue on segment {seg} outside palette mapping")
    chapter_cues = [
        c for c in cues if isinstance(c, dict) and str(c.get("placement")) in {"after_segment", "before_segment"}
    ]
    chapter_assets = {
        str(c.get("asset_id"))
        for c in chapter_cues
        if isinstance(c, dict) and str(c.get("asset_id")) in asset_ids
    }
    if len(chapter_cues) > 1 and len(chapter_assets) > 1:
        errors.append("chapter_stinger reuse expected: multiple chapter cues should share one stinger asset")
    return errors


def _lint_sound_design_plan_flow2(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    cfg = merged_config()
    cap = int((cfg.get("sound_design") or {}).get("max_assets_flow2", 4))
    assets = artifacts.get("assets") or []
    if len(assets) > cap:
        errors.append(f"asset count {len(assets)} exceeds cap {cap}")
    ranks: set[int] = set()
    if ctx.artifact_exists("flow_2_highlights/selection.json"):
        sel = ctx.read_json("flow_2_highlights/selection.json")
        for clip in sel.get("clips") or sel.get("highlights") or []:
            if isinstance(clip, dict) and clip.get("rank") is not None:
                ranks.add(int(clip["rank"]))
    cues = ((artifacts.get("flow_plans") or {}).get("flow2") or {}).get("cues") or []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        for key in ("from_clip_rank", "to_clip_rank"):
            r = cue.get(key)
            if r is not None and ranks and int(r) not in ranks:
                errors.append(f"cue rank {key}={r} not in highlight selection")
    between = [c for c in cues if isinstance(c, dict) and c.get("placement") == "between_clips"]
    transition_assets = {
        str(c.get("asset_id")) for c in between if isinstance(c, dict) and c.get("asset_id")
    }
    if len(between) > 1 and len(transition_assets) > 1:
        errors.append("transition_stinger reuse expected: between_clips cues should share one transition asset")
    return errors


def _lint_sfx_prompt_craft(artifacts: dict[str, Any], _ctx: RunContext) -> list[str]:
    errors: list[str] = []
    prompts = artifacts.get("prompts") or []
    if not prompts:
        return ["no crafted prompts"]
    mmaudio_cfg = (merged_config().get("mmaudio") or {})
    min_gen = float(mmaudio_cfg.get("min_duration_sec", 3.0))
    max_gen = float(mmaudio_cfg.get("max_duration_sec", 8.0))
    sonic_keywords = _sonic_tag_keywords(_ctx)
    allow_diegetic = bool((merged_config().get("sound_design") or {}).get("allow_diegetic_ambient", False))
    for row in prompts:
        if not isinstance(row, dict):
            continue
        aid = row.get("asset_id")
        text = str(row.get("sfx_prompt", ""))
        neg = str(row.get("negative_prompt", ""))
        words = len(text.split())
        if words < 40:
            errors.append(f"prompt for {aid} under 40 words ({words})")
        neg_words = len(neg.split())
        if neg_words < 12:
            errors.append(f"negative_prompt for {aid} under 12 words ({neg_words})")
        if neg_words > 60:
            errors.append(f"negative_prompt for {aid} over 60 words ({neg_words})")
        neg_low = neg.lower()
        if not any(tok in neg_low for tok in ("vocal", "speech", "lyric")):
            errors.append(f"negative_prompt for {aid} must ban vocals/speech/lyrics")
        for field_name, field_text in (("sfx_prompt", text), ("negative_prompt", neg)):
            for pat in _FORBIDDEN_MMAUDIO_STRINGS:
                if pat.search(field_text):
                    errors.append(f"{field_name} for {aid} contains forbidden API reference")
                    break
        if re.search(r"\bavoid:\b", text, re.I) or re.search(r"\bno vocals\b", text, re.I):
            errors.append(f"positive prompt for {aid} should not contain Avoid/no vocals clauses")
        if sonic_keywords:
            prompt_tokens = {w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text)}
            if not (prompt_tokens & sonic_keywords):
                errors.append(f"prompt for {aid} has low keyword overlap with sonic_context tags")
        for pat in _SPEECH_LYRICS_PATTERNS:
            if pat.search(text):
                errors.append(f"prompt for {aid} contains speech/lyrics pattern")
                break
        role = str(row.get("role", ""))
        if role == "ambient_bed" and not allow_diegetic and _DIEGETIC_HINTS.search(text):
            errors.append(f"prompt for {aid} requests diegetic ambient while disabled")
        dur = float(row.get("duration_seconds") or 0)
        band = _ROLE_DURATION_BANDS.get(role)
        if band and dur and not (band[0] <= dur <= band[1]):
            errors.append(f"duration {dur}s out of band for role {role}")
        if dur and not (min_gen <= dur <= max_gen + 0.5):
            errors.append(f"duration {dur}s outside MMAudio plan clamp")
        cfg = row.get("cfg_strength")
        if cfg is not None and not (2.0 <= float(cfg) <= 8.0):
            errors.append(f"cfg_strength for {aid} outside 2.0–8.0")
    return errors


def _sonic_tag_keywords(ctx: RunContext) -> set[str]:
    sonic = load_sonic_context(ctx) or {}
    out: set[str] = set()
    for row in sonic.get("tag_registry") or []:
        if not isinstance(row, dict):
            continue
        for keyword in row.get("keywords") or []:
            token = str(keyword or "").strip().lower()
            if token:
                out.add(token)
    return out


def _gap_report_vo_lines(ctx: RunContext) -> list[str]:
    lines: list[str] = []
    if ctx.artifact_exists("understanding/gap_report.json"):
        gr = ctx.read_json("understanding/gap_report.json")
        for line in gr.get("interviewer_lines") or []:
            if isinstance(line, dict):
                lines.append(str(line.get("text", "")).lower())
    return lines


def transition_gap_overlap_errors(transitions: list[Any], ctx: RunContext) -> list[str]:
    """Soft cross-validate: transition text duplicates gap_report VO."""
    errors: list[str] = []
    gap_lines = _gap_report_vo_lines(ctx)
    for tr in transitions:
        if not isinstance(tr, dict):
            continue
        low = str(tr.get("text", "")).lower()
        for gl in gap_lines:
            if gl and len(gl) > 10 and gl in low:
                errors.append("transition duplicates gap_report VO line")
                break
    return errors


def _lint_transitions(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    transitions = artifacts.get("transitions") or []
    for tr in transitions:
        if not isinstance(tr, dict):
            continue
        words = len(str(tr.get("text", "")).split())
        if words > 30:
            errors.append(f"transition exceeds 30 words ({words})")
    errors.extend(transition_gap_overlap_errors(transitions, ctx))
    return errors


def _lint_full_master_ranking(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    ordered = artifacts.get("ordered_segment_ids") or []
    manifest_ids = _manifest_ids(ctx)
    if manifest_ids:
        for sid in ordered:
            if str(sid) not in manifest_ids:
                errors.append(f"ordered segment {sid} not in manifest")
    excluded = artifacts.get("excluded_segment_ids") or []
    if excluded and not artifacts.get("exclude_rationales"):
        errors.append("excluded segments without exclude_rationales")
    return errors


def _lint_optimal_questions(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    lines = artifacts.get("interviewer_lines") or []
    line_ids = {str(ln.get("line_id")) for ln in lines if isinstance(ln, dict) and ln.get("line_id")}
    for ln in lines:
        if isinstance(ln, dict) and not ln.get("line_id"):
            errors.append("interviewer_line missing line_id")
            break
    if ctx.artifact_exists("understanding/gap_evaluations.json"):
        evals = ctx.read_json("understanding/gap_evaluations.json")
        high_segs = {
            str(r.get("segment_id"))
            for r in (evals.get("evaluations") or [])
            if isinstance(r, dict) and str(r.get("severity", "")).lower() == "high"
        }
        targeted = {
            str(ln.get("targets_segment_id") or ln.get("segment_id") or "")
            for ln in lines
            if isinstance(ln, dict)
        }
        for seg_id in high_segs:
            if seg_id and seg_id not in targeted:
                errors.append(f"high gap segment {seg_id} has no interviewer line")
                break
    if not lines and not errors:
        pass
    return errors


def _lint_topic_coverage_audit(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    if artifacts.get("coverage_score") is None:
        errors.append("coverage_score missing")
    topic_names: set[str] = set()
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        for t in (brief.get("topics") or []) if isinstance(brief, dict) else []:
            if isinstance(t, dict) and t.get("name"):
                topic_names.add(str(t["name"]).strip().lower())
    for item in artifacts.get("missing_coverage") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("topic") or item.get("topic_name") or "").strip().lower()
        if name and topic_names and name not in topic_names:
            errors.append(f"missing_coverage topic {name!r} not in brief")
            break
    from interview_mux.coherence import coherence_active
    from interview_mux.coherence.duration_gate import coherence_activated
    from interview_mux.coherence.paths import COHERENCE_REPORT_PATH

    if coherence_active() and coherence_activated(ctx) and ctx.artifact_exists(COHERENCE_REPORT_PATH):
        report = ctx.read_json(COHERENCE_REPORT_PATH)
        open_risks = [
            r
            for r in (report.get("risks") or [])
            if isinstance(r, dict) and r.get("status", "open") == "open"
        ]
        if open_risks and not artifacts.get("missing_coverage"):
            errors.append(
                "coherence: open coherence risks exist but coverage_audit.missing_coverage is empty"
            )
    return errors


def _lint_narrative_arc_plan(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    cfg = merged_config()
    max_ch = int((cfg.get("analysis") or {}).get("prompt_thresholds", {}).get("max_chapters", 8))
    chapters = artifacts.get("chapters") or []
    if len(chapters) > max_ch:
        errors.append(f"chapter count {len(chapters)} exceeds max {max_ch}")
    manifest_ids = _manifest_ids(ctx)
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        seg_ids = ch.get("segment_ids") or []
        if not seg_ids:
            errors.append(f"chapter {ch.get('chapter_id')} has no segment_ids")
        for sid in seg_ids:
            if manifest_ids and str(sid) not in manifest_ids:
                errors.append(f"chapter segment {sid} not in manifest")
                break
    for constraint in artifacts.get("ordering_constraints") or []:
        if not isinstance(constraint, dict):
            continue
        for sid in constraint.get("segment_ids") or constraint.get("ordered_segment_ids") or []:
            if manifest_ids and str(sid) not in manifest_ids:
                errors.append(f"ordering_constraint segment {sid} not in manifest")
                break
    return errors


def _lint_edl_narrative_audit(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    errors: list[str] = []
    verdict = str(artifacts.get("verdict", "")).strip().lower()
    if verdict not in ("pass", "warn", "fail"):
        errors.append(f"invalid verdict {verdict!r}")
    selection_ids: set[str] = set()
    if ctx.artifact_exists("flow_1_master/selection.json"):
        sel = ctx.read_json("flow_1_master/selection.json")
        selection_ids = {str(x) for x in (sel.get("ordered_segment_ids") or [])}
    for issue in artifacts.get("blocking_issues") or artifacts.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        sid = issue.get("segment_id")
        if sid and selection_ids and str(sid) not in selection_ids:
            errors.append(f"audit issue cites segment {sid} not in selection")
            break
    return errors


def _lint_podcast_show_description(artifacts: dict[str, Any], _ctx: RunContext) -> list[str]:
    errors: list[str] = []
    cfg = merged_config()
    min_w = int(cfg.get("show_description_min_words", 150))
    max_w = int(cfg.get("show_description_max_words", 250))
    wc = artifacts.get("word_count")
    if wc is not None:
        wc_int = int(wc)
        if wc_int < min_w or wc_int > max_w:
            errors.append(f"word_count {wc_int} outside {min_w}-{max_w}")
    md = str(artifacts.get("description_markdown") or "").strip()
    if not md:
        errors.append("description_markdown empty")
    return errors


def _lint_legacy_sfx_brief(artifacts: dict[str, Any], ctx: RunContext, *, flow: str) -> list[str]:
    errors: list[str] = []
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        sdp = ctx.read_json("understanding/sound_design_plan.json")
        assets = sdp.get("assets") or []
        if assets:
            errors.append("SDP assets exist — prefer sound_design_plan_flow* over legacy brief")
    cap = 6 if flow == "flow1" else 4
    cues = artifacts.get("cues") or artifacts.get("sfx_cues") or []
    if len(cues) > cap:
        errors.append(f"legacy brief cue count {len(cues)} exceeds cap {cap}")
    return errors


def _lint_podcast_sfx_brief(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    return _lint_legacy_sfx_brief(artifacts, ctx, flow="flow1")


def _lint_sfx_brief(artifacts: dict[str, Any], ctx: RunContext) -> list[str]:
    return _lint_legacy_sfx_brief(artifacts, ctx, flow="flow2")


def _lint_generic(
    stage_key: str,
    envelope: dict[str, Any],
    ctx: RunContext,
    schema_errors: list[str] | None,
    *,
    truncation_flags: list[str] | None = None,
    routed_via_collate: bool = False,
) -> list[str]:
    errors: list[str] = []
    from interview_mux.arbiter_expectations import rubric_for_stage
    from interview_mux.llm_flow_hardening import producer_artifact_path
    from interview_mux.llm_preflight import run_preflight

    rubric = rubric_for_stage(stage_key) or {}
    keys = set(rubric.get("deterministic_lint_keys") or [])
    artifacts = _artifacts(envelope)
    flags = truncation_flags or []

    if "envelope_status_complete" in keys and envelope.get("status") != "complete":
        errors.append("envelope_status_complete: status is not complete")

    trunc_meta = (envelope.get("_llm_meta") or {}).get("truncation_escalation") or {}
    if trunc_meta.get("final_flags") and envelope.get("status") == "complete":
        errors.append(
            f"truncation_unresolved: {trunc_meta.get('final_flags')[:2]}"
        )

    if "schema_errors_empty" in keys and schema_errors:
        errors.append(f"schema_errors_empty: {'; '.join(schema_errors[:2])}")

    if "confidence_gte_min" in keys:
        reconcile_envelope_confidence(stage_key, envelope)
        min_conf = float(rubric.get("min_confidence_on_accept", 0.75) or 0.75)
        conf = float(envelope.get("confidence") or 0)
        if conf < min_conf:
            errors.append(f"confidence_gte_min: {conf} < {min_conf}")

    if "producer_artifact_complete" in keys:
        from interview_mux.artifact_completeness import compute_gaps

        rel = producer_artifact_path(stage_key)
        if rel:
            if not artifacts:
                errors.append(f"producer_artifact_complete: {rel} no envelope artifacts")
            else:
                gap_paths = [
                    g.path for g in compute_gaps(rel, artifacts, stage_key=stage_key)
                ]
                if gap_paths:
                    errors.append(
                        f"producer_artifact_complete: {rel} gaps: {gap_paths[0]}"
                    )

    if "upstream_artifacts_complete" in keys:
        pf = run_preflight(stage_key, ctx)
        if pf:
            errors.append(f"upstream_artifacts_complete: {pf[0]}")

    if "cross_artifact_refs_valid" in keys:
        universe = _reference_id_universe(ctx, stage_key)
        refs = collect_segment_ids_from_artifacts(stage_key, artifacts)
        if universe and refs:
            orphans = sorted(refs - universe)
            if orphans:
                errors.append(
                    f"cross_artifact_refs_valid: segment id(s) not in reference set: {', '.join(orphans[:3])}"
                )

    if "segment_coverage_ratio" in keys:
        manifest_ids = _manifest_ids(ctx)
        if manifest_ids:
            covered = _coverage_numerator(stage_key, artifacts)
            ratio = len(covered & manifest_ids) / len(manifest_ids)
            default_min = 1.0 if len(manifest_ids) < 5 else 0.85
            min_ratio = float(rubric.get("min_segment_coverage_ratio", default_min) or default_min)
            if ratio < min_ratio:
                errors.append(
                    f"segment_coverage_ratio: {ratio:.2f} < {min_ratio} "
                    f"({len(covered & manifest_ids)}/{len(manifest_ids)} segments)"
                )

    if "min_row_count_met" in keys:
        if stage_key == "speaker_roles":
            speakers = artifacts.get("speakers") or []
            if not speakers:
                errors.append("min_row_count_met: speakers list empty")
        elif stage_key == "boundary_detection":
            boundaries = artifacts.get("boundaries") or []
            if _transcript_duration_ms(ctx) > 60_000 and not boundaries:
                errors.append("min_row_count_met: no boundaries on long interview")

    if "truncation_requires_decompose" in keys:
        decompose = bool(rubric.get("decompose_eligible"))
        if (
            decompose
            and flags
            and envelope.get("status") == "complete"
            and not routed_via_collate
        ):
            errors.append(
                f"truncation_requires_decompose: flags {flags[:2]} without shard/collate path"
            )

    if "truncation_flags_absent" in keys and flags:
        errors.append(f"truncation_flags_absent: unexpected truncation {flags[:2]}")

    return errors


def _lint_highlight_selection(artifacts: dict[str, Any], _ctx: RunContext) -> list[str]:
    errors: list[str] = []
    clips = artifacts.get("clips") or artifacts.get("highlights") or []
    cfg = merged_config()
    cap = int((merged_config().get("analysis") or {}).get("prompt_thresholds", {}).get(
        "max_highlight_clips", 5
    ))
    if len(clips) > cap:
        errors.append(f"more than {cap} highlight clips")
    return errors


_LINTERS: dict[str, Any] = {
    "speaker_roles": _lint_speaker_roles,
    "content_context": _lint_content_context,
    "boundary_detection": _lint_boundary_detection,
    "segment_classification": _lint_segment_classification,
    "content_brief_reanchor": _lint_content_brief_reanchor,
    "missing_framing": _lint_missing_framing,
    "sound_design_palettes": _lint_sound_design_palettes,
    "sound_design_plan_flow1": _lint_sound_design_plan_flow1,
    "sound_design_plan_flow2": _lint_sound_design_plan_flow2,
    "sfx_prompt_craft": _lint_sfx_prompt_craft,
    "sfx_prompt_refine": _lint_sfx_prompt_craft,
    "transitions": _lint_transitions,
    "full_master_ranking": _lint_full_master_ranking,
    "highlight_selection": _lint_highlight_selection,
    "optimal_questions": _lint_optimal_questions,
    "topic_coverage_audit": _lint_topic_coverage_audit,
    "narrative_arc_plan": _lint_narrative_arc_plan,
    "edl_narrative_audit": _lint_edl_narrative_audit,
    "podcast_show_description": _lint_podcast_show_description,
    "podcast_sfx_brief": _lint_podcast_sfx_brief,
    "sfx_brief": _lint_sfx_brief,
}


def lint_remediation_hint(error: str) -> str | None:
    low = error.lower()
    if "all speakers unknown" in low or (
        "interviewer" in low and ("speaker" in low or "speakers.json" in low)
    ):
        return "Re-run Speaker roles and verify interviewer or moderator assignment."
    if "truncation_requires_decompose" in low:
        return "Next retry will use decompose/shard path — or shorten transcript input."
    if "confidence_gte_min" in low:
        return "Next retry will use flagship tier model."
    if (
        "generic theme" in low
        or "key_claim without evidence" in low
        or "topic without evidence" in low
    ):
        return "Anchor topics and claims with segment_ids or approx_time_range from the transcript."
    if "thesis empty" in low:
        return "Produce a concrete one-sentence thesis from interviewee statements."
    if "producer_artifact_complete" in low:
        return "Envelope artifact incomplete — check required fields in the schema."
    if "segment_coverage_ratio" in low:
        return "Include every required_segment_id from classification_obligation; retry may use per-segment decompose."
    if "all segments typed interviewee_answer" in low:
        return "Vary types (interviewer_question, setup, reaction) per segment-classification taxonomy."
    if "manifest times not monotonic" in low:
        return "Fix segments/boundaries.json timeline — re-run from boundary_detection."
    return None


def lint_remediation_hints(lint_errors: list[str]) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()
    for err in lint_errors:
        hint = lint_remediation_hint(err)
        if hint and hint not in seen:
            seen.add(hint)
            hints.append(hint)
    return hints


def deterministic_lint(
    stage_key: str,
    envelope: dict[str, Any],
    ctx: RunContext,
    *,
    schema_errors: list[str] | None = None,
    truncation_flags: list[str] | None = None,
    volley: list[dict[str, str]] | None = None,
    routed_via_collate: bool = False,
) -> list[str]:
    """Return human-readable lint errors (empty = pass)."""
    from interview_mux.context_volley import truncation_flags_for_volley

    flags = truncation_flags
    if flags is None and volley:
        flags = truncation_flags_for_volley(volley)
    errors: list[str] = []
    try:
        errors.extend(
            _lint_generic(
                stage_key,
                envelope,
                ctx,
                schema_errors,
                truncation_flags=flags,
                routed_via_collate=routed_via_collate,
            )
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"lint internal error (generic): {exc}")
    fn = _LINTERS.get(stage_key)
    if fn:
        try:
            errors.extend(fn(_artifacts(envelope), ctx))
        except Exception as exc:  # noqa: BLE001 — lint must not crash pipeline
            errors.append(f"lint internal error: {exc}")
    return errors[:16]
