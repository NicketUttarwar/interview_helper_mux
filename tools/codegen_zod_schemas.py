#!/usr/bin/env python3
"""Generate Zod schemas from docs/cross-cutting/json-schemas for GUI validation."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCHEMAS_ROOT = REPO / "docs" / "cross-cutting" / "json-schemas"
OUT_DIR = REPO / "frontend" / "src" / "schemas" / "generated"

# rel_path -> schema file (under json-schemas/)
ARTIFACT_SCHEMA_FILES: dict[str, str] = {
    "understanding/analysis_state.json": "analysis_state.schema.json",
    "understanding/content_brief.json": "artifacts/content_brief_artifact.schema.json",
    "understanding/speakers.json": "artifacts/speakers_artifact.schema.json",
    "understanding/sound_design_plan.json": "sound_design_plan.schema.json",
    "understanding/investigation_queue.json": "investigation_queue.schema.json",
    "understanding/context_index.json": "context_index.schema.json",
    "understanding/gap_evaluations.json": "artifacts/gap_evaluations_artifact.schema.json",
    "understanding/gap_report.json": "gap_report.schema.json",
    "understanding/source_acoustic_profile.json": "source_acoustic_profile.schema.json",
    "segments/boundaries.json": "artifacts/boundaries_artifact.schema.json",
    "segments/manifest.json": "artifacts/manifest_artifact.schema.json",
    "flow_1_master/coverage_audit.json": "artifacts/coverage_audit_artifact.schema.json",
    "flow_1_master/narrative_plan.json": "artifacts/narrative_plan_artifact.schema.json",
    "flow_1_master/selection.json": "artifacts/master_selection_artifact.schema.json",
    "flow_1_master/transitions.json": "artifacts/transitions_artifact.schema.json",
    "flow_1_master/podcast_sfx_brief.json": "artifacts/podcast_sfx_artifact.schema.json",
    "flow_1_master/edl_narrative_audit.json": "artifacts/edl_narrative_audit_artifact.schema.json",
    "flow_1_master/edl.json": "artifacts/edl_flow1.schema.json",
    "flow_2_highlights/selection.json": "artifacts/highlights_artifact.schema.json",
    "flow_2_highlights/sfx_brief.json": "artifacts/sfx_montage_artifact.schema.json",
    "flow_3_description/show_description.json": "artifacts/show_description_artifact.schema.json",
    "sound_design/elevenlabs_prompts.json": "artifacts/elevenlabs_prompts_artifact.schema.json",
    "sound_design/placement_adjustments.json": "placement_adjustments.schema.json",
    "run_meta.json": "run_meta.schema.json",
    "transcript/corrections.json": "transcript_corrections.schema.json",
    "transcript/disfluencies.json": "disfluencies.schema.json",
    "segments/nle_edits.json": "nle_edits.schema.json",
    "transcript/review_queue.json": "transcript_review.schema.json",
}


def _safe_name(rel: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", rel).strip("_")
    return f"{base}Schema"


def _emit_type(prop: dict[str, Any], *, name: str = "value") -> str:
    t = prop.get("type")
    if isinstance(prop.get("enum"), list):
        vals = ", ".join(json.dumps(v) for v in prop["enum"])
        return f"z.enum([{vals}])"
    if t == "string":
        inner = "z.string()"
        if prop.get("minLength"):
            inner += f".min({prop['minLength']})"
        return inner
    if t == "number" or t == "integer":
        return "z.number()"
    if t == "boolean":
        return "z.boolean()"
    if t == "array":
        items = prop.get("items") or {}
        return f"z.array({_emit_type(items, name=name + 'Item')})"
    if t == "object":
        return _emit_object(prop, name=name)
    return "z.unknown()"


def _emit_object(schema: dict[str, Any], *, name: str) -> str:
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    lines: list[str] = []
    for key, prop in props.items():
        zt = _emit_type(prop, name=f"{name}_{key}")
        if key not in required:
            zt += ".optional()"
        lines.append(f"  {json.dumps(key)}: {zt},")
    if not lines:
        return "z.record(z.string(), z.unknown())"
    return "z.object({\n" + "\n".join(lines) + "\n})"


def schema_to_zod(schema: dict[str, Any], export_name: str) -> str:
    root = _emit_object(schema, name=export_name)
    return (
        "// Auto-generated — do not edit. Run: python tools/codegen_zod_schemas.py\n"
        "import { z } from \"zod\";\n\n"
        f"export const {export_name} = {root};\n"
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index_lines = [
        "// Auto-generated registry — do not edit.",
        "import { z } from \"zod\";",
        "",
    ]
    imports: list[str] = []
    registry: list[str] = []

    for rel, filename in sorted(ARTIFACT_SCHEMA_FILES.items()):
        path = SCHEMAS_ROOT / filename
        if not path.is_file():
            print(f"skip missing schema: {path}")
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        export = _safe_name(rel)
        out_file = OUT_DIR / f"{export}.ts"
        out_file.write_text(schema_to_zod(schema, export), encoding="utf-8")
        imports.append(f'import {{ {export} }} from "./{export}";')
        registry.append(f'  {json.dumps(rel)}: {export},')
        print(f"wrote {out_file.relative_to(REPO)}")

    index_lines.extend(imports)
    index_lines.append("")
    index_lines.append("export const artifactWriteSchemas: Record<string, z.ZodTypeAny> = {")
    index_lines.extend(registry)
    index_lines.append("};")
    index_lines.append("")

    (OUT_DIR / "index.ts").write_text("\n".join(index_lines), encoding="utf-8")
    print(f"wrote {OUT_DIR / 'index.ts'}")


if __name__ == "__main__":
    main()
