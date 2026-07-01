"""Unified post-call verification for OpenAI and local MLX responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator

from interview_mux.local_structured_output import verify_local_response
from interview_mux.openai_structured_output import (
    compose_arbiter_schema,
    compose_envelope_schema,
    compose_specialist_envelope_schema,
    load_schema_file,
    resolve_parent_stage_key,
    resolve_specialist_key,
)
from interview_mux.prompt_validation import (
    STAGE_ARTIFACT_SCHEMAS,
    validate_envelope,
    validate_stage_artifacts,
)


@dataclass
class VerificationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    schema_name: str = ""
    interaction_id: str = ""


def _validate_against_schema(data: Any, schema: dict[str, Any], *, prefix: str = "") -> list[str]:
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    pfx = f"{prefix}." if prefix else ""
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in err.path)
        loc = f"{pfx}{path}" if path else prefix or "root"
        errors.append(f"{loc}: {err.message}")
    return errors


def verify_llm_response(
    interaction_id: str,
    parsed: dict[str, Any],
    *,
    stage_key: str | None = None,
    task_kind: str | None = None,
) -> VerificationResult:
    """Dispatch verification by catalog interaction_id."""
    if interaction_id == "OM-02":
        schema = compose_arbiter_schema(strict=False)
        errors = _validate_against_schema(parsed, schema, prefix="arbiter")
        return VerificationResult(
            ok=not errors,
            errors=errors,
            schema_name="arbiter_verdict",
            interaction_id=interaction_id,
        )

    if interaction_id.startswith("LX-"):
        interaction = "itr_clarification" if interaction_id.startswith("LX-02") else "local_framer"
        errors = verify_local_response(interaction, parsed)
        return VerificationResult(
            ok=not errors,
            errors=errors,
            schema_name=interaction,
            interaction_id=interaction_id,
        )

    if interaction_id.startswith("OS-"):
        sk = _specialist_key_for_id(interaction_id) or resolve_specialist_key(stage_key or "")
        if sk:
            schema = compose_specialist_envelope_schema(sk, strict=False)
            errors = _validate_against_schema(parsed, schema, prefix="envelope")
            errors.extend(validate_envelope(parsed))
            artifact_schema = load_schema_file(f"specialists/{sk}.schema.json")
            if artifact_schema:
                errors.extend(
                    _validate_against_schema(
                        parsed.get("artifacts") or {},
                        artifact_schema,
                        prefix="artifacts",
                    )
                )
            return VerificationResult(
                ok=not errors,
                errors=errors,
                schema_name=f"specialists/{sk}",
                interaction_id=interaction_id,
            )

    parent = resolve_parent_stage_key(stage_key or "")
    if parent in STAGE_ARTIFACT_SCHEMAS or interaction_id.startswith(("OA-", "OF-", "OM-")):
        errors = list(validate_envelope(parsed))
        if parent in STAGE_ARTIFACT_SCHEMAS:
            errors.extend(validate_stage_artifacts(parent, parsed.get("artifacts") or {}))
            if not errors:
                try:
                    schema = compose_envelope_schema(parent, strict=False)
                    errors.extend(_validate_against_schema(parsed, schema, prefix="envelope"))
                except (KeyError, FileNotFoundError):
                    pass
        schema_name = STAGE_ARTIFACT_SCHEMAS.get(parent, "analysis_envelope")
        return VerificationResult(
            ok=not errors,
            errors=errors,
            schema_name=schema_name,
            interaction_id=interaction_id,
        )

    return VerificationResult(ok=True, errors=[], schema_name="", interaction_id=interaction_id)


def _specialist_key_for_id(interaction_id: str) -> str | None:
    mapping = {
        "OS-01": "comprehension_risk_blind",
        "OS-02": "theme_coverage_pass",
        "OS-03": "emphasis_coverage_pass",
    }
    return mapping.get(interaction_id)


def verification_to_record_dict(result: VerificationResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "errors": result.errors[:20],
        "schema_name": result.schema_name,
        "interaction_id": result.interaction_id,
    }
