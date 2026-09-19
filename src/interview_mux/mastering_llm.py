"""Mastering prompt invokes (A-03 Shape/research LLM cutover).

Canon: docs/prompts/mastering/. Max 2 attempts per stage invoke.
Callers gate via research_llm_enabled / shape_llm_enabled.
Shape LLM default on (Q6B) with packed payloads + response lint; research.llm stays off.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from interview_mux.run_context import RunContext

_MASTERING_ARTIFACT_SCHEMAS = {
    "agenda": ("mastering_shape_agenda", "mastering_shape_agenda.schema.json"),
    "rubric": ("mastering_eval_rubric", "mastering_eval_rubric.schema.json"),
    "candidates": (
        "mastering_shape_candidates",
        "mastering_shape_candidates.schema.json",
    ),
}
_MASTERING_NESTED_KEYS = frozenset(
    required for required, _schema in _MASTERING_ARTIFACT_SCHEMAS.values()
)


def artifacts_from_envelope(envelope: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize envelope artifacts; None when unusable."""
    if not isinstance(envelope, dict):
        return None
    arts = envelope.get("artifacts")
    if isinstance(arts, dict) and arts:
        return arts
    # Shape prompts can arrive as a normalized envelope body with the named
    # artifact nested directly (rather than below ``artifacts``).
    nested = {key: envelope[key] for key in _MASTERING_NESTED_KEYS if key in envelope}
    if nested:
        return nested
    # Some runners return the artifact object as the envelope body.
    if envelope.get("version") == 1 and (
        "narrative_mode" in envelope
        or "fields" in envelope
        or "candidates" in envelope
        or "mode_candidates" in envelope
        or "steps" in envelope
        or "criteria" in envelope
    ):
        return dict(envelope)
    return None


def _artifact_contract(
    user_payload: dict[str, Any] | str,
) -> tuple[str, str] | None:
    if not isinstance(user_payload, dict):
        return None
    return _MASTERING_ARTIFACT_SCHEMAS.get(
        str(user_payload.get("artifact") or "").strip().lower()
    )


def _contract_response_format(required: str, schema_file: str) -> dict[str, Any]:
    from interview_mux.openai_structured_output import (
        compose_envelope_schema_from_artifact,
        load_schema_file,
    )

    schema = load_schema_file(f"artifacts/{schema_file}") or load_schema_file(schema_file)
    if not schema:
        raise FileNotFoundError(schema_file)
    artifacts_schema = {
        "type": "object",
        "properties": {required: schema},
        "required": [required],
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": f"{required}_response"[:64],
            "strict": True,
            "schema": compose_envelope_schema_from_artifact(
                artifacts_schema, strict=True
            ),
        },
    }


def classify_mastering_artifact_failure(
    artifacts: dict[str, Any] | None,
    *,
    required_artifact: str,
    schema_file: str,
) -> tuple[str | None, list[str]]:
    """Return WS1's typed hollow class and schema details."""
    if not isinstance(artifacts, dict) or not artifacts:
        return "empty_primary", ["artifacts: empty"]
    named = artifacts.get(required_artifact)
    other_named = [
        key for key in _MASTERING_NESTED_KEYS if key != required_artifact and key in artifacts
    ]
    if not isinstance(named, dict):
        if other_named:
            return "wrong_artifact_envelope", [
                f"expected {required_artifact}; received {other_named[0]}"
            ]
        # Legacy flat artifact bodies remain ingestible when schema-valid.
        named = artifacts
    if not named:
        return "empty_primary", [f"{required_artifact}: empty"]
    if required_artifact == "mastering_shape_candidates" and not named.get("candidates"):
        return "empty_primary", ["candidates: empty"]
    try:
        from interview_mux.prompt_validation import (
            validate_mastering_eval_rubric,
            validate_mastering_shape_agenda,
            validate_mastering_shape_candidates,
        )

        validator = {
            "mastering_shape_agenda.schema.json": validate_mastering_shape_agenda,
            "mastering_eval_rubric.schema.json": validate_mastering_eval_rubric,
            "mastering_shape_candidates.schema.json": validate_mastering_shape_candidates,
        }[schema_file]
        errors = validator(named)
    except Exception as exc:
        errors = [f"contract validation failed: {type(exc).__name__}"]
    return ("schema_invalid", errors) if errors else (None, [])


def mastering_failure_predicate_token(
    stage_key: str, failure_class: str, errors: list[str]
) -> str:
    """Stable fingerprint used by driver identical-failure caps."""
    canonical = json.dumps(
        [stage_key, failure_class, sorted(str(e) for e in errors)],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def invoke_mastering_prompt(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    user_payload: dict[str, Any] | str,
    *,
    max_attempts: int = 2,
) -> dict[str, Any] | None:
    """Call a mastering system prompt; return artifacts dict or None (fail-open)."""
    try:
        from interview_mux.stages.llm_runner import run_prompt_envelope
    except Exception:
        return None

    if isinstance(user_payload, str):
        user_content = user_payload
    else:
        try:
            user_content = json.dumps(user_payload, ensure_ascii=False, default=str)
        except Exception:
            return None

    contract = _artifact_contract(user_payload)
    response_format = None
    if contract is not None:
        response_format = _contract_response_format(*contract)
    attempts = max(1, min(int(max_attempts or 2), 2))
    last_failure: tuple[str, list[str]] | None = None
    for attempt in range(1, attempts + 1):
        attempt_content = user_content
        if attempt > 1 and last_failure is not None:
            failure_class, errors = last_failure
            remutate = {
                "kind": "typed_contract_remutate",
                "failure_class": failure_class,
                "instruction": (
                    "Remutate once. Return exactly the required named artifact "
                    "and satisfy its bound JSON schema."
                ),
                "schema_errors": errors[:5],
            }
            try:
                body = json.loads(user_content)
                if isinstance(body, dict):
                    body["remutate"] = remutate
                    attempt_content = json.dumps(body, ensure_ascii=False, default=str)
            except Exception:
                attempt_content = f"{user_content}\n\n{json.dumps(remutate)}"
        try:
            envelope = run_prompt_envelope(
                stage_key,
                prompt_rel,
                user_content=attempt_content,
                ctx=ctx,
                include_preamble=True,
                call_attempt=attempt,
                response_format=response_format,
                record_stage_key=(
                    "mastering_eval_rubric"
                    if contract and contract[0] == "mastering_eval_rubric"
                    else None
                ),
            )
        except Exception as exc:
            last_failure = ("schema_invalid", [str(exc)[:500]])
            continue
        arts = artifacts_from_envelope(envelope if isinstance(envelope, dict) else None)
        if contract is not None:
            failure_class, errors = classify_mastering_artifact_failure(
                arts,
                required_artifact=contract[0],
                schema_file=contract[1],
            )
            if failure_class is not None:
                last_failure = (failure_class, errors)
                continue
        if arts is not None:
            return arts
        status = ""
        if isinstance(envelope, dict):
            status = str(envelope.get("status") or "").lower()
        if status in ("complete",) and isinstance(envelope, dict):
            nested = envelope.get("artifacts")
            if isinstance(nested, dict):
                return nested
    if contract is not None and last_failure is not None:
        from interview_mux.llm_simple import StageError

        failure_class, errors = last_failure
        token = mastering_failure_predicate_token(stage_key, failure_class, errors)
        raise StageError(
            stage_key,
            "typed_mastering_remutate_halt:"
            f"{failure_class}:predicate_token={token}:"
            f"{'; '.join(errors[:2])}",
        )
    return None
