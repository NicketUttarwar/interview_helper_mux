"""Listen-quality heuristics for assembly / pre-master soft gates."""

from __future__ import annotations

from typing import Any


def vo_density_issues(
    edl: dict[str, Any] | None,
    *,
    max_consecutive_vo: int = 3,
    max_vo_ratio: float = 0.35,
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


def evaluate_listen_critic(
    *,
    ordered: list[str],
    edl: dict[str, Any] | None = None,
    story_health: dict[str, Any] | None = None,
    hook_segment_id: str | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    issues.extend(hook_presence_issues(ordered, hook_segment_id))
    issues.extend(vo_density_issues(edl))
    if isinstance(story_health, dict):
        for row in story_health.get("issues") or []:
            if isinstance(row, dict) and row.get("code") in {
                "finale_tail",
                "ordering_constraint",
            }:
                issues.append(
                    {
                        "code": f"story_{row.get('code')}",
                        "severity": "warn" if story_health.get("nle_overlay_applied") else row.get("severity", "warn"),
                        "message": row.get("message"),
                    }
                )
    errors = [i for i in issues if i.get("severity") == "error"]
    # Soft-gate: only empty order hard-fails; chronology softens to warn for ship-always
    verdict = "fail" if errors else ("warn" if issues else "pass")
    return {
        "version": 1,
        "verdict": verdict,
        "issues": issues,
        "error_count": len(errors),
        "warning_count": sum(1 for i in issues if i.get("severity") == "warn"),
    }
