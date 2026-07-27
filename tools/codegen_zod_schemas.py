#!/usr/bin/env python3
"""Generate Zod schemas from docs/cross-cutting/json-schemas for GUI validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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
    "understanding/interview_spine.json": "interview_spine.schema.json",
    "understanding/coherence_report.json": "coherence_report.schema.json",
    "understanding/sonic_context.json": "sonic_context.schema.json",
    "segments/boundaries.json": "artifacts/boundaries_artifact.schema.json",
    "segments/manifest.json": "artifacts/manifest_artifact.schema.json",
    "master/coverage_audit.json": "artifacts/coverage_audit_artifact.schema.json",
    "master/narrative_plan.json": "artifacts/narrative_plan_artifact.schema.json",
    "master/selection.json": "artifacts/master_selection_artifact.schema.json",
    "master/transitions.json": "artifacts/transitions_artifact.schema.json",
    "master/podcast_sfx_brief.json": "artifacts/podcast_sfx_artifact.schema.json",
    "master/edl_narrative_audit.json": "artifacts/edl_narrative_audit_artifact.schema.json",
    "master/edl.json": "artifacts/edl.schema.json",
    "show_notes/show_description.json": "artifacts/show_description_artifact.schema.json",
    "sound_design/sfx_prompts.json": "artifacts/sfx_prompts_artifact.schema.json",
    "sound_design/mmaudio_qa.json": "artifacts/mmaudio_qa.schema.json",
    "sound_design/placement_adjustments.json": "placement_adjustments.schema.json",
    "run_meta.json": "run_meta.schema.json",
    "transcript/corrections.json": "transcript_corrections.schema.json",
    "transcript/disfluencies.json": "disfluencies.schema.json",
    "segments/nle_edits.json": "nle_edits.schema.json",
    "transcript/review_queue.json": "transcript_review.schema.json",
    "understanding/refinement_agenda.json": "refinement_agenda.schema.json",
    "understanding/refinement_ledger.json": "refinement_ledger.schema.json",
    "understanding/refinement_plan.json": "refinement_plan.schema.json",
}

def _safe_name(rel: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", rel).strip("_")
    return f"{base}Schema"

def _type_branches(prop: dict[str, Any]) -> tuple[list[str], bool]:
    t = prop.get("type")
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        return non_null, "null" in t
    if t:
        return [t], False
    return [], False

def _with_constraints(inner: str, prop: dict[str, Any], *, is_array: bool = False) -> str:
    if is_array:
        if prop.get("minItems") is not None:
            inner += f".min({prop['minItems']})"
        if prop.get("maxItems") is not None:
            inner += f".max({prop['maxItems']})"
        return inner
    if prop.get("type") == "string" or (
        isinstance(prop.get("type"), list) and "string" in prop.get("type", [])
    ):
        if prop.get("minLength") is not None:
            inner += f".min({prop['minLength']})"
        if prop.get("maxLength") is not None:
            inner += f".max({prop['maxLength']})"
    return inner

def _emit_type(prop: dict[str, Any], *, name: str = "value") -> str:
    if isinstance(prop.get("enum"), list):
        vals = ", ".join(json.dumps(v) for v in prop["enum"])
        inner = f"z.enum([{vals}])"
    elif "const" in prop:
        inner = f"z.literal({json.dumps(prop['const'])})"
    else:
        types, nullable = _type_branches(prop)
        if len(types) != 1:
            inner = "z.unknown()"
        else:
            t = types[0]
            if t == "string":
                inner = _with_constraints("z.string()", prop)
            elif t == "number" or t == "integer":
                inner = "z.number()"
            elif t == "boolean":
                inner = "z.boolean()"
            elif t == "array":
                items = prop.get("items") or {}
                item_zod = _emit_type(items, name=name + "Item")
                inner = _with_constraints(f"z.array({item_zod})", prop, is_array=True)
            elif t == "object":
                inner = _emit_object(prop, name=name)
            else:
                inner = "z.unknown()"
        _, nullable = _type_branches(prop)
        if nullable:
            inner += ".nullable()"

    return inner

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
    loader_entries: list[str] = []

    for rel, filename in sorted(ARTIFACT_SCHEMA_FILES.items()):
        path = SCHEMAS_ROOT / filename
        if not path.is_file():
            print(f"skip missing schema: {path}")
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        export = _safe_name(rel)
        out_file = OUT_DIR / f"{export}.ts"
        out_file.write_text(schema_to_zod(schema, export), encoding="utf-8")
        loader_entries.append(
            f'  {json.dumps(rel)}: async () =>\n'
            f'    (await import("./{export}")).{export},'
        )
        print(f"wrote {out_file.relative_to(REPO)}")

    index_lines = [
        "// Auto-generated registry — do not edit.",
        "import type { z } from \"zod\";",
        "",
        "const schemaLoaders: Record<string, () => Promise<z.ZodTypeAny>> = {",
        *loader_entries,
        "};",
        "",
        "const schemaCache = new Map<string, z.ZodTypeAny>();",
        "",
        "export const artifactWriteSchemaPaths = Object.keys(schemaLoaders);",
        "",
        "export async function loadArtifactWriteSchema(",
        "  path: string,",
        "): Promise<z.ZodTypeAny | null> {",
        "  const loader = schemaLoaders[path];",
        "  if (!loader) return null;",
        "  const cached = schemaCache.get(path);",
        "  if (cached) return cached;",
        "  const schema = await loader();",
        "  schemaCache.set(path, schema);",
        "  return schema;",
        "}",
        "",
        "/** Fire-and-forget warm-up for editor UX */",
        "export function prefetchArtifactWriteSchema(path: string): void {",
        "  void loadArtifactWriteSchema(path);",
        "}",
        "",
    ]

    (OUT_DIR / "index.ts").write_text("\n".join(index_lines), encoding="utf-8")
    print(f"wrote {OUT_DIR / 'index.ts'}")

if __name__ == "__main__":
    main()
