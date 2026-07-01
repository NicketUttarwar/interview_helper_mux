#!/usr/bin/env python3
"""Pre-compose OpenAI strict envelope+artifact schemas into docs/cross-cutting/json-schemas/composed/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.openai_structured_output import (  # noqa: E402
    compose_arbiter_schema,
    compose_envelope_schema,
    composed_cache_dir,
)
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS  # noqa: E402


def main() -> int:
    out_dir = composed_cache_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    arbiter_path = out_dir / "arbiter_verdict.openai.json"
    arbiter_path.write_text(
        json.dumps(compose_arbiter_schema(strict=True), indent=2) + "\n",
        encoding="utf-8",
    )

    for stage_key, artifact_file in sorted(STAGE_ARTIFACT_SCHEMAS.items()):
        schema = compose_envelope_schema(stage_key, strict=True)
        name = f"analysis_envelope_{stage_key}.openai.json"
        (out_dir / name).write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {name} ({artifact_file})")

    print(f"composed {len(STAGE_ARTIFACT_SCHEMAS) + 1} schemas → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
