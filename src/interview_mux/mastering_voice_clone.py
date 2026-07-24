"""Voice-clone consent, scope, and audit trail.

Spec: docs/cross-cutting/mastering-voice-clone-policy.md
Schema: mastering_voice_clone_audit.schema.json
Artifact: mastering/voice_clone_audit.json

Least-spoken eligibility is an editorial rule; it is not authorization. Cloning a
guest / content speaker is banned outright and no config value relaxes that.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.conversation_context import role_is_frame
from interview_mux.mastering_hardening_config import gate_cfg, gate_mode
from interview_mux.run_context import RunContext
from interview_mux.source_topology import pickup_eligible_speaker_id

CloneScope = Literal["cold_open", "bridges", "outro"]

AUDIT_ARTIFACT = "mastering/voice_clone_audit.json"
VALID_SCOPES: tuple[str, ...] = ("cold_open", "bridges", "outro")
VALID_DISCLOSURES: tuple[str, ...] = ("none", "show_notes", "in_audio")

CLONE_COLD_OPEN_KINDS: frozenset[str] = frozenset({"vo_clone_open", "vo_plus_segment"})


class CloneNotAuthorized(RuntimeError):
    """Raised when a clone is requested without a complete authorization chain."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_meta(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists("run_meta.json"):
        doc = ctx.read_json("run_meta.json")
        if isinstance(doc, dict):
            return doc
    return {}


def empty_consent() -> dict[str, Any]:
    return {
        "speaker_id": None,
        "granted": False,
        "granted_by": None,
        "granted_at": None,
        "scopes": [],
        "reference_path": None,
        "reference_approved": False,
        "disclosure": "none",
        "revoked_at": None,
    }


def load_consent(ctx: RunContext) -> dict[str, Any]:
    raw = _run_meta(ctx).get("voice_clone_consent")
    if not isinstance(raw, dict):
        return empty_consent()
    return {**empty_consent(), **raw}


def consent_hash(consent: dict[str, Any]) -> str:
    payload = {k: consent.get(k) for k in ("speaker_id", "granted_at", "scopes", "reference_path")}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def grant_consent(
    ctx: RunContext,
    *,
    speaker_id: str,
    scopes: list[str],
    granted_by: str = "operator",
    disclosure: str = "none",
) -> dict[str, Any]:
    """Record explicit clone consent for the pickup-eligible speaker."""
    from interview_mux.conversation_context import load_conversation_context

    bad_scopes = [s for s in scopes if s not in VALID_SCOPES]
    if bad_scopes:
        raise ValueError(f"unknown clone scopes: {', '.join(bad_scopes)}")
    if disclosure not in VALID_DISCLOSURES:
        raise ValueError(f"unknown disclosure value: {disclosure}")

    eligible = pickup_eligible_speaker_id(ctx)
    if not eligible:
        raise CloneNotAuthorized(
            "speaker_unidentified", "No pickup-eligible speaker is confirmed for this run"
        )
    if speaker_id != eligible:
        raise CloneNotAuthorized(
            "guest_clone_attempted",
            f"{speaker_id} is not the pickup-eligible speaker ({eligible}); "
            "cloning a content speaker is never permitted",
        )

    conv = load_conversation_context(ctx)
    role = str((conv.speaker_by_id.get(speaker_id) or {}).get("role") or "")
    if not role_is_frame(role):
        raise CloneNotAuthorized(
            "guest_clone_attempted",
            f"{speaker_id} has role '{role}', which is not a frame role; cloning is banned",
        )

    rel = f"understanding/voice_reference/{speaker_id}.json"
    ref_doc = ctx.read_json(rel) if ctx.artifact_exists(rel) else {}
    approved = isinstance(ref_doc, dict) and bool(ref_doc.get("approved"))

    consent = {
        **empty_consent(),
        "speaker_id": speaker_id,
        "granted": True,
        "granted_by": granted_by,
        "granted_at": _now(),
        "scopes": [s for s in VALID_SCOPES if s in scopes],
        "reference_path": rel,
        "reference_approved": approved,
        "disclosure": disclosure,
    }

    def patch(meta: dict[str, Any]) -> None:
        meta["voice_clone_consent"] = consent

    ctx.mutate_run_meta(patch)
    return consent


def revoke_consent(ctx: RunContext) -> dict[str, Any]:
    consent = load_consent(ctx)
    consent["granted"] = False
    consent["revoked_at"] = _now()

    def patch(meta: dict[str, Any]) -> None:
        meta["voice_clone_consent"] = consent

    ctx.mutate_run_meta(patch)
    return consent


def consent_active(consent: dict[str, Any]) -> bool:
    return bool(consent.get("granted")) and not consent.get("revoked_at")


def authorization_error(
    consent: dict[str, Any],
    *,
    speaker_id: str | None,
    scope: str,
    pickup_speaker_id: str | None,
    speaker_role: str | None = None,
) -> tuple[str, str] | None:
    """Return `(code, detail)` when the authorization chain is incomplete, else None."""
    if speaker_role is not None and not role_is_frame(speaker_role):
        return (
            "guest_clone_attempted",
            f"{speaker_id} has role '{speaker_role}'; cloning a content speaker is banned",
        )
    if not speaker_id:
        return ("speaker_unidentified", "clone requested for an unidentified speaker")
    if not pickup_speaker_id:
        return ("speaker_not_pickup_eligible", "no pickup-eligible speaker is confirmed")
    if speaker_id != pickup_speaker_id:
        return (
            "guest_clone_attempted",
            f"{speaker_id} is not the pickup-eligible speaker ({pickup_speaker_id})",
        )
    if consent.get("revoked_at"):
        return ("consent_revoked", f"clone consent was revoked at {consent['revoked_at']}")
    if not consent.get("granted"):
        return ("consent_missing", "no clone consent recorded for this run")
    if not consent.get("reference_approved"):
        return ("reference_not_approved", "voice reference sample is not approved")
    if scope not in (consent.get("scopes") or []):
        return ("scope_not_granted", f"clone consent does not cover scope '{scope}'")
    return None


def clone_authorized(ctx: RunContext, *, scope: str) -> bool:
    consent = load_consent(ctx)
    return (
        authorization_error(
            consent,
            speaker_id=consent.get("speaker_id"),
            scope=scope,
            pickup_speaker_id=pickup_eligible_speaker_id(ctx),
        )
        is None
    )


def require_clone_authorized(ctx: RunContext, *, scope: str) -> None:
    """Hard gate for synthesis call sites. Blocks in authoritative mode only,
    except the guest-clone ban, which always blocks."""
    consent = load_consent(ctx)
    err = authorization_error(
        consent,
        speaker_id=consent.get("speaker_id"),
        scope=scope,
        pickup_speaker_id=pickup_eligible_speaker_id(ctx),
    )
    if not err:
        return
    code, detail = err
    if code == "guest_clone_attempted" or gate_mode("voice_clone") == "authoritative":
        raise CloneNotAuthorized(code, detail)
    ctx.log(
        f"Voice clone advisory: {detail}",
        level="warning",
        stage="mastering",
        detail={"event": "voice_clone_advisory", "code": code, "scope": scope},
    )


def cold_open_clone_allowed(ctx: RunContext, cold_open: dict[str, Any]) -> tuple[bool, str | None]:
    """Whether a `vo_clone_*` cold open may be planned for this run."""
    kind = str((cold_open or {}).get("kind") or "none")
    if kind not in CLONE_COLD_OPEN_KINDS:
        return True, None
    consent = load_consent(ctx)
    err = authorization_error(
        consent,
        speaker_id=cold_open.get("vo_voice_speaker_id") or consent.get("speaker_id"),
        scope="cold_open",
        pickup_speaker_id=pickup_eligible_speaker_id(ctx),
    )
    if err is None:
        return True, None
    return False, err[1]


def build_audit(
    *,
    consent: dict[str, Any],
    utterances: list[dict[str, Any]],
    violations: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chash = consent_hash(consent)
    rows: list[dict[str, Any]] = []
    for utt in utterances:
        row = dict(utt)
        row.setdefault("recorded_at", _now())
        if row.get("origin") == "synthesized_clone":
            row.setdefault("consent_hash", chash)
        rows.append(row)
    conf = gate_cfg("voice_clone", cfg)
    payload = {
        "version": 1,
        "mode": gate_mode("voice_clone", cfg),
        "consent": consent,
        "utterances": rows,
        "violations": list(violations or []),
        "generated_at": _now(),
    }
    if conf.get("require_disclosure") and consent.get("disclosure") == "none":
        payload["violations"].append(
            {
                "code": "consent_missing",
                "detail": "config requires a disclosure but the run recorded 'none'",
            }
        )
    return payload


def write_audit(ctx: RunContext, audit: dict[str, Any]) -> None:
    ctx.write_json(AUDIT_ARTIFACT, audit)


def consent_payload(ctx: RunContext) -> dict[str, Any]:
    """Operator-surface fields for the G-VoiceRef gate."""
    consent = load_consent(ctx)
    eligible = pickup_eligible_speaker_id(ctx)
    return {
        "voice_clone_consent": consent,
        "voice_clone_scopes": list(consent.get("scopes") or []),
        "voice_clone_consent_active": consent_active(consent),
        "voice_clone_consent_pending": not consent_active(consent) and bool(eligible),
        "voice_clone_available_scopes": list(VALID_SCOPES),
        "voice_clone_disclosure_options": list(VALID_DISCLOSURES),
        "voice_clone_mode": gate_mode("voice_clone"),
    }
