#!/usr/bin/env python3
"""Verify stage contract coverage vs code registries."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from interview_mux.openai_structured_output import compose_envelope_schema  # noqa: E402
from interview_mux.openai_schema_lint import lint_openai_strict_schema  # noqa: E402
from interview_mux.openai_schema_semantic_lint import lint_openai_semantic_schema  # noqa: E402
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS  # noqa: E402
from interview_mux.stage_contract import all_contract_stage_ids, contracts_dir, load_contract  # noqa: E402

SCHEMA = contracts_dir() / "_contract-schema.json"


def main() -> int:
    errors: list[str] = []
    contract_ids = set(all_contract_stage_ids())
    for sid in STAGE_ARTIFACT_SCHEMAS:
        if sid not in contract_ids:
            errors.append(f"missing contract YAML for LLM stage {sid}")
        else:
            c = load_contract(sid)
            if c and not c.sufficiency:
                errors.append(f"LLM stage {sid} contract missing sufficiency block")

    for sid in sorted(STAGE_ARTIFACT_SCHEMAS):
        schema = compose_envelope_schema(sid, strict=True)
        errors.extend(lint_openai_strict_schema(schema))
        errors.extend(lint_openai_semantic_schema(schema))

    for path in sorted(contracts_dir().glob("*.yaml")):
        if path.stem.startswith("_"):
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not raw.get("stage_id"):
            errors.append(f"invalid contract: {path.name}")

    if errors:
        print("verify_stage_contracts FAILED:")
        for e in errors[:25]:
            print(f"  - {e}")
        return 1
    print(f"verify_stage_contracts OK ({len(contract_ids)} contracts, {len(STAGE_ARTIFACT_SCHEMAS)} LLM stages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
