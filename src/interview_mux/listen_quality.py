"""Listen-quality heuristics for assembly / pre-master soft gates."""

from __future__ import annotations

from typing import Any


def vo_density_issues(
    edl: dict[str, Any] | None,
    *,
    max_consecutive_vo: int = 3,
    max_vo_ratio: float = 0.25,
) -> list[dict[str, Any]]:
    """Flag VO walls and excessive synthetic share on the EDL timeline."""
    if not isinstance(edl, dict):
        return []
    clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    if not clips:
        return []
    issues: list[dict[str, Any]] = []
    consecutive = 0
    vo_ms = 0
    total_ms = 0
    for clip in clips:
        dur = int(clip.get("duration_ms") or 0)
        total_ms += max(0, dur)
        ctype = str(clip.get("type") or "")
        if ctype in {"vo_pickup", "transition"}:
            consecutive += 1
            vo_ms += max(0, dur)
            if consecutive > max_consecutive_vo:
                issues.append(
                    {
                        "code": "vo_wall",
                        "severity": "warn",
                        "message": f"more than {max_consecutive_vo} consecutive synthetic clips",
                    }
                )
                consecutive = 0  # avoid spamming
        else:
            consecutive = 0
    if total_ms > 0 and (vo_ms / total_ms) > max_vo_ratio:
        issues.append(
            {
                "code": "vo_density_high",
                "severity": "warn",
                "message": f"synthetic share {vo_ms / total_ms:.0%} exceeds {max_vo_ratio:.0%}",
            }
        )
    return issues


def hook_presence_issues(ordered: list[str], hook_segment_id: str | None) -> list[dict[str, Any]]:
    if not ordered:
        return [
            {
                "code": "empty_order",
                "severity": "error",
                "message": "no ordered segments for hook check",
            }
        ]
    if not hook_segment_id:
        return []
    early = set(ordered[:3])
    if str(hook_segment_id) not in early:
        return [
            {
                "code": "weak_open",
                "severity": "warn",
                "message": f"declared hook {hook_segment_id} not in first three slots",
            }
        ]
    return []


def pacing_budget_issues(
    ordered: list[str],
    segments_by_id: dict[str, dict[str, Any]] | None = None,
    *,
    soft_max_ms: int | None = None,
    narrative_plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Soft master duration + chapter time-share skew."""
    issues: list[dict[str, Any]] = []
    by_id = segments_by_id or {}
    total = 0
    for sid in ordered:
        seg = by_id.get(sid) or {}
        try:
            start = int(seg.get("start_ms") or seg.get("source_start_ms") or 0)
            end = int(seg.get("end_ms") or seg.get("source_end_ms") or start)
            total += max(0, end - start)
        except (TypeError, ValueError):
            continue
    if soft_max_ms and total > soft_max_ms:
        issues.append(
            {
                "code": "over_duration_budget",
                "severity": "warn",
                "message": f"selected speech ~{total}ms exceeds soft max {soft_max_ms}ms",
            }
        )
    if isinstance(narrative_plan, dict) and by_id:
        chapters = [c for c in (narrative_plan.get("chapters") or []) if isinstance(c, dict)]
        if len(chapters) >= 2 and total > 0:
            shares: list[float] = []
            for ch in chapters:
                ch_ms = 0
                for sid in ch.get("segment_ids") or []:
                    if str(sid) not in ordered:
                        continue
                    seg = by_id.get(str(sid)) or {}
                    try:
                        start = int(seg.get("start_ms") or 0)
                        end = int(seg.get("end_ms") or start)
                        ch_ms += max(0, end - start)
                    except (TypeError, ValueError):
                        pass
                shares.append(ch_ms / total)
            if shares and max(shares) > 0.65:
                issues.append(
                    {
                        "code": "act_share_skew",
                        "severity": "warn",
                        "message": f"one act holds {max(shares):.0%} of selected time",
                    }
                )
    return issues


def energy_arc_issues(
    ordered: list[str],
    segments_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Avoid stacking three long/heavy blocks without relief."""
    by_id = segments_by_id or {}
    if len(ordered) < 3:
        return []
    heavy_run = 0
    for sid in ordered:
        seg = by_id.get(sid) or {}
        try:
            start = int(seg.get("start_ms") or 0)
            end = int(seg.get("end_ms") or start)
            dur = end - start
        except (TypeError, ValueError):
            dur = 0
        tags = {str(t).lower() for t in (seg.get("topic_tags") or []) if t}
        heavy = dur >= 90_000 or bool(tags & {"grief", "conflict", "trauma", "finance", "legal"})
        heavy_run = heavy_run + 1 if heavy else 0
        if heavy_run >= 3:
            return [
                {
                    "code": "energy_arc_stack",
                    "severity": "warn",
                    "message": "three consecutive heavy/long blocks without relief",
                }
            ]
    return []


def anti_redundancy_issues(
    ordered: list[str],
    segments_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Flag near-duplicate split siblings both kept when one may suffice."""
    import re

    by_id = segments_by_id or {}
    issues: list[dict[str, Any]] = []
    for i in range(len(ordered) - 1):
        a, b = ordered[i], ordered[i + 1]
        m1 = re.match(r"^(seg_\d+)([a-z]+)?$", a)
        m2 = re.match(r"^(seg_\d+)([a-z]+)?$", b)
        if not m1 or not m2 or m1.group(1) != m2.group(1):
            continue
        sa, sb = by_id.get(a) or {}, by_id.get(b) or {}
        ta = str(sa.get("text") or sa.get("transcript") or "")[:200].lower()
        tb = str(sb.get("text") or sb.get("transcript") or "")[:200].lower()
        if ta and tb and ta == tb:
            issues.append(
                {
                    "code": "redundant_split_sibling",
                    "severity": "warn",
                    "message": f"split siblings {a}/{b} share identical text — consider dropping one",
                }
            )
    return issues


def air_breath_issues(edl: dict[str, Any] | None, *, min_silence_ms: int = 180) -> list[dict[str, Any]]:
    """Flag hard butt-splices after VO before answers (no silence air pad)."""
    if not isinstance(edl, dict):
        return []
    clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    issues: list[dict[str, Any]] = []
    for i in range(len(clips) - 1):
        cur, nxt = clips[i], clips[i + 1]
        ctype = str(cur.get("type") or "")
        ntype = str(nxt.get("type") or "")
        if ctype in {"vo_pickup", "transition"} and ntype in {"speech", "segment"}:
            issues.append(
                {
                    "code": "butt_splice_after_vo",
                    "severity": "warn",
                    "message": (
                        f"VO/transition directly butts speech "
                        f"(want ≥{min_silence_ms}ms air)"
                    ),
                }
            )
            if len(issues) >= 4:
                break
        if ctype in {"vo_pickup", "transition"} and ntype == "silence":
            sil = int(nxt.get("duration_ms") or 0)
            if sil < min_silence_ms and i + 2 < len(clips):
                after = str(clips[i + 2].get("type") or "")
                if after in {"speech", "segment"}:
                    issues.append(
                        {
                            "code": "thin_air_after_vo",
                            "severity": "warn",
                            "message": f"only {sil}ms air after VO before speech",
                        }
                    )
    return issues


def question_answerability_issues(
    gap_report: dict[str, Any] | None,
    segments_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Framing questions should land before a clip that can answer them."""
    if not isinstance(gap_report, dict):
        return []
    by_id = segments_by_id or {}
    issues: list[dict[str, Any]] = []
    for ln in gap_report.get("interviewer_lines") or []:
        if not isinstance(ln, dict):
            continue
        cat = str(ln.get("line_category") or ln.get("category") or "").lower()
        text = str(ln.get("text") or "").strip()
        if "?" not in text and "question" not in cat and "framing" not in cat:
            continue
        target = str(ln.get("targets_segment_id") or "")
        if not target:
            issues.append(
                {
                    "code": "question_no_target",
                    "severity": "warn",
                    "message": f"framing question {ln.get('line_id')} has no targets_segment_id",
                }
            )
            continue
        seg = by_id.get(target) or {}
        body = str(seg.get("text") or seg.get("transcript") or "").strip()
        if by_id and not body:
            issues.append(
                {
                    "code": "question_empty_answer_clip",
                    "severity": "warn",
                    "message": f"question targets {target} but clip text is empty",
                }
            )
    return issues[:8]


def music_hinge_issues(sound_design_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Theme/punctuator cues should exist for cold open / hinges when plan declares them."""
    if not isinstance(sound_design_plan, dict):
        return []
    assets = [a for a in (sound_design_plan.get("assets") or []) if isinstance(a, dict)]
    roles = {str(a.get("role") or "") for a in assets}
    issues: list[dict[str, Any]] = []
    # Soft: if any theme role present but cold open missing when cold_open cues exist
    cues = sound_design_plan.get("cues") or sound_design_plan.get("placements") or []
    cue_roles = {
        str(c.get("role") or c.get("kind") or "")
        for c in cues
        if isinstance(c, dict)
    }
    wants_cold = any("cold" in r for r in cue_roles) or "theme_cold_open" in roles
    if wants_cold and "theme_cold_open" not in roles and not any("cold" in r for r in roles):
        issues.append(
            {
                "code": "missing_cold_open_theme",
                "severity": "warn",
                "message": "cold-open music cue declared but no theme_cold_open asset role",
            }
        )
    # Required episode close: theme_outro cue must exist when config/plan requires music.
    require_outro = True
    try:
        from interview_mux.information_packages import information_packages_cfg

        require_outro = bool(
            (information_packages_cfg().get("episode_close") or {}).get("require_music", True)
        )
    except Exception:
        require_outro = True
    has_outro_cue = any(
        isinstance(c, dict)
        and not c.get("skip")
        and (
            str(c.get("role") or "") == "theme_outro"
            or "outro" in str(c.get("cue_id") or "").lower()
        )
        for c in cues
    )
    if require_outro and "theme_outro" not in roles and not has_outro_cue:
        issues.append(
            {
                "code": "missing_episode_close_outro",
                "severity": "error",
                "message": "episode_close requires a theme_outro cue after the last native",
            }
        )
    elif require_outro and "theme_outro" in roles and not has_outro_cue:
        issues.append(
            {
                "code": "missing_episode_close_outro_cue",
                "severity": "error",
                "message": "theme_outro asset present but no after-last-native outro cue",
            }
        )
    return issues


def evaluate_listen_critic(
    *,
    ordered: list[str],
    edl: dict[str, Any] | None = None,
    story_health: dict[str, Any] | None = None,
    hook_segment_id: str | None = None,
    segments_by_id: dict[str, dict[str, Any]] | None = None,
    narrative_plan: dict[str, Any] | None = None,
    gap_report: dict[str, Any] | None = None,
    sound_design_plan: dict[str, Any] | None = None,
    soft_max_ms: int | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    issues.extend(hook_presence_issues(ordered, hook_segment_id))
    issues.extend(vo_density_issues(edl))
    issues.extend(
        pacing_budget_issues(
            ordered,
            segments_by_id,
            soft_max_ms=soft_max_ms,
            narrative_plan=narrative_plan,
        )
    )
    issues.extend(energy_arc_issues(ordered, segments_by_id))
    issues.extend(anti_redundancy_issues(ordered, segments_by_id))
    issues.extend(air_breath_issues(edl))
    issues.extend(question_answerability_issues(gap_report, segments_by_id))
    issues.extend(music_hinge_issues(sound_design_plan))
    if isinstance(story_health, dict):
        for row in story_health.get("issues") or []:
            if isinstance(row, dict) and row.get("code") in {
                "finale_tail",
                "ordering_constraint",
            }:
                issues.append(
                    {
                        "code": f"story_{row.get('code')}",
                        "severity": "warn"
                        if story_health.get("nle_overlay_applied")
                        else row.get("severity", "warn"),
                        "message": row.get("message"),
                    }
                )
    errors = [i for i in issues if i.get("severity") == "error"]
    warns = [i for i in issues if i.get("severity") == "warn"]
    # Soft-gate: only empty order hard-fails; chronology softens to warn for ship-always
    verdict = "fail" if errors else ("warn" if issues else "pass")
    # Quality score 0–100 for G-Listen borderline
    score = 100.0 - 25.0 * len(errors) - 6.0 * len(warns)
    score = max(0.0, min(100.0, score))
    return {
        "version": 1,
        "verdict": verdict,
        "issues": issues,
        "error_count": len(errors),
        "warning_count": len(warns),
        "quality_score": round(score, 1),
        "g_listen_recommended": bool(score < 72.0 and (errors or warns)),
    }


def ensure_hook_early(
    ordered: list[str],
    hook_segment_id: str | None,
) -> tuple[list[str], bool]:
    """Move declared hook into the first three slots when missing. Returns (order, moved)."""
    if not hook_segment_id or not ordered:
        return list(ordered), False
    hid = str(hook_segment_id)
    if hid not in ordered:
        return list(ordered), False
    if hid in ordered[:3]:
        return list(ordered), False
    out = [s for s in ordered if s != hid]
    out.insert(0, hid)
    return out, True
