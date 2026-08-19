"""In-process MCP-shaped tool catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from interview_mux.config import repo_root
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

AUDIO_MUTATING = frozenset(
    {
        "mix",
        "master_finalize",
        "audio_preclean",
        "transcribe",
        "mmaudio_sfx",
        "run_musicgen",
        "run_mmaudio",
        "run_chatterbox",
        "run_s2s",
        "run_deepfilter",
        "ears_stt_window",
        "ears_s2s_window",
    }
)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    kind: str  # stage | host | llm | operator_action | prompt | rail
    identity: str
    mutating_audio: bool = False
    nested_llm: bool = False
    host: Callable[..., Any] | None = None
    prompt_rel: str | None = None
    out_of_scope: bool = False


def openai_tools_payload(specs: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description[:1024],
                "parameters": s.parameters or {"type": "object", "properties": {}},
            },
        }
        for s in specs
        if not s.out_of_scope
    ]


def stage_tool_specs() -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for stage in (*ANALYSIS_ORDER, *DELIVERY_ORDER):
        specs.append(
            ToolSpec(
                name=f"run_stage_{stage}",
                description=(
                    f"Run pipeline stage {stage} (host callable from pipeline.py)."
                    + (
                        " After G0 is closed this is refused — pack g0_transcript instead of re-STT."
                        if stage in {"transcribe", "ingest", "audio_preclean"}
                        else ""
                    )
                ),
                parameters={
                    "type": "object",
                    "properties": {"stage": {"type": "string", "const": stage}},
                },
                kind="stage",
                identity=stage,
                mutating_audio=stage in AUDIO_MUTATING
                or stage
                in {"mmaudio_sfx", "mix", "master_finalize", "audio_preclean", "transcribe"},
            )
        )
    specs.extend(
        [
            ToolSpec(
                name="admit_result",
                description="Admit a tool output: keep, reformat, or drop.",
                parameters={
                    "type": "object",
                    "properties": {
                        "identity": {"type": "string"},
                        "action": {"type": "string", "enum": ["keep", "reformat", "drop"]},
                        "fact_id": {"type": "string"},
                    },
                    "required": ["identity", "action"],
                },
                kind="host",
                identity="admit_result",
            ),
            ToolSpec(
                name="pack_volley",
                description="Select fact IDs; host renders user/assistant turns (no free-write).",
                parameters={
                    "type": "object",
                    "properties": {
                        "tool_id": {"type": "string"},
                        "fact_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["tool_id", "fact_ids"],
                },
                kind="host",
                identity="pack_volley",
            ),
            ToolSpec(
                name="persist_artifact",
                description="Write an artifact after keep/reformat admit.",
                parameters={
                    "type": "object",
                    "properties": {
                        "rel": {"type": "string"},
                        "fact_id": {"type": "string"},
                    },
                    "required": ["rel", "fact_id"],
                },
                kind="host",
                identity="persist_artifact",
            ),
            ToolSpec(
                name="analyze_issue",
                description="One analysis per problem signature.",
                parameters={
                    "type": "object",
                    "properties": {
                        "issue_id": {"type": "string"},
                        "quality_hypothesis": {"type": "string"},
                        "action": {"type": "string"},
                        "style": {"type": "string"},
                        "docs_cited": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["issue_id", "quality_hypothesis", "action"],
                },
                kind="llm",
                identity="analyze_issue",
                nested_llm=True,
            ),
            ToolSpec(
                name="retrieve_canon",
                description="Top-k documentation chunks from docs/INDEX and canon.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "k": {"type": "integer"},
                    },
                    "required": ["query"],
                },
                kind="host",
                identity="retrieve_canon",
            ),
            ToolSpec(
                name="read_json",
                description="Read a run artifact JSON (tape meaning; no run_meta dumps).",
                parameters={
                    "type": "object",
                    "properties": {"rel": {"type": "string"}},
                    "required": ["rel"],
                },
                kind="host",
                identity="read_json",
            ),
            ToolSpec(
                name="ears_stt_window",
                description="Slice audio and re-STT for QC (does not overwrite Apple VTT).",
                parameters={
                    "type": "object",
                    "properties": {
                        "rel": {"type": "string"},
                        "start_ms": {"type": "integer"},
                        "end_ms": {"type": "integer"},
                        "window_id": {"type": "string"},
                    },
                    "required": ["window_id"],
                },
                kind="host",
                identity="ears_stt_window",
                mutating_audio=True,
            ),
            ToolSpec(
                name="end_judgment",
                description="Holistic accept/reject after a complete master.wav.",
                parameters={
                    "type": "object",
                    "properties": {
                        "verdict": {"type": "string", "enum": ["accept", "reject"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["verdict"],
                },
                kind="llm",
                identity="end_judgment",
                nested_llm=True,
            ),
            ToolSpec(
                name="shape_pre_critique_gates",
                description="Run Shape L2–L4 pre-critique hardening gates (diversity/feasibility/integrity/auditions).",
                parameters={"type": "object", "properties": {}},
                kind="host",
                identity="shape_pre_critique_gates",
            ),
            ToolSpec(
                name="shape_post_critique_gates",
                description="Run Shape L4 post-critique Pareto / remaining hardening gates.",
                parameters={"type": "object", "properties": {}},
                kind="host",
                identity="shape_post_critique_gates",
            ),
            ToolSpec(
                name="build_speaker_dossier",
                description="Map diarized ids to names/roles from tape; never invent names.",
                parameters={"type": "object", "properties": {}},
                kind="host",
                identity="build_speaker_dossier",
            ),
            ToolSpec(
                name="run_musicgen",
                description=(
                    "Host MusicGen generate. Prefers large; host ladder is large→medium→small "
                    "then MMAudio backup. Same callable stages use."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "role": {"type": "string"},
                        "duration_sec": {"type": "number"},
                        "model_id": {"type": "string"},
                        "out_rel": {"type": "string"},
                    },
                },
                kind="host",
                identity="run_musicgen",
                mutating_audio=True,
            ),
            ToolSpec(
                name="run_mmaudio",
                description="Host MMAudio generate. Backup after MusicGen ladder for creative beds.",
                parameters={"type": "object", "properties": {"prompt": {"type": "string"}}},
                kind="host",
                identity="run_mmaudio",
                mutating_audio=True,
            ),
            ToolSpec(
                name="run_chatterbox",
                description="Host Chatterbox VO (local).",
                parameters={"type": "object", "properties": {"text": {"type": "string"}}},
                kind="host",
                identity="run_chatterbox",
                mutating_audio=True,
            ),
            ToolSpec(
                name="run_s2s",
                description="Host speech-to-speech (local mlx).",
                parameters={"type": "object", "properties": {"text": {"type": "string"}}},
                kind="host",
                identity="run_s2s",
                mutating_audio=True,
            ),
            ToolSpec(
                name="run_deepfilter",
                description="Host DeepFilterNet enhance (local).",
                parameters={"type": "object", "properties": {}},
                kind="host",
                identity="run_deepfilter",
                mutating_audio=True,
            ),
            ToolSpec(
                name="verify_master",
                description="Host loudness/verify_master check on master.wav.",
                parameters={"type": "object", "properties": {}},
                kind="host",
                identity="verify_master",
            ),
            ToolSpec(
                name="set_gate",
                description="Gate controller: open / auto_resolve / present_operator / skip a category. G0 cannot skip.",
                parameters={
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "action": {
                            "type": "string",
                            "enum": ["open", "auto_resolve", "present_operator", "skip"],
                        },
                    },
                    "required": ["category", "action"],
                },
                kind="host",
                identity="set_gate",
            ),
            ToolSpec(
                name="promote_prompt",
                description="Promote a minted prompt only if eval-corpus passed.",
                parameters={
                    "type": "object",
                    "properties": {
                        "mint_id": {"type": "string"},
                        "corpus_ok": {"type": "boolean"},
                    },
                    "required": ["mint_id"],
                },
                kind="host",
                identity="promote_prompt",
            ),
            ToolSpec(
                name="mint_prompt",
                description="Mint a prompt module (OpenAI or MLX shorter variant). Promotion is separate and corpus-gated.",
                parameters={
                    "type": "object",
                    "properties": {
                        "mint_id": {"type": "string"},
                        "body": {"type": "string"},
                        "runtime": {"type": "string", "enum": ["openai", "mlx"]},
                    },
                    "required": ["mint_id", "body"],
                },
                kind="host",
                identity="mint_prompt",
            ),
            ToolSpec(
                name="stack_prompt_module",
                description="Attach a conductor/perspective module to the next volley stack.",
                parameters={
                    "type": "object",
                    "properties": {"module": {"type": "string"}},
                    "required": ["module"],
                },
                kind="host",
                identity="stack_prompt_module",
            ),
            ToolSpec(
                name="skip_stage",
                description=(
                    "Skip a remaining stage with a reason. Island fuse stages and "
                    "required analysis stages (content_context, talking_points, "
                    "ideal_cuts, boundary_detection, episode_structure, chapter_close_hitch) cannot skip "
                    "without their artifacts. After a span/coverage failure, rerun "
                    "that stage instead of skipping."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "stage": {"type": "string"},
                        "reason": {"type": "string"},
                        "compensating_fact": {"type": "string"},
                    },
                    "required": ["stage", "reason"],
                },
                kind="host",
                identity="skip_stage",
            ),
            ToolSpec(
                name="schedule_stage",
                description="Reorder: run this stage next (optionally before another id).",
                parameters={
                    "type": "object",
                    "properties": {
                        "stage": {"type": "string"},
                        "before": {"type": "string"},
                    },
                    "required": ["stage"],
                },
                kind="host",
                identity="schedule_stage",
            ),
            ToolSpec(
                name="rerun_stage",
                description="Surgical re-run of one done stage with extra facts. Does not clear downstream. After G0 is closed, transcribe/ingest/audio_preclean are refused — pack g0_transcript instead. Do not rerun segment_classification when segments/manifest.json already has segment_id and speaker_role — pack segment_manifest for gap eval.",
                parameters={
                    "type": "object",
                    "properties": {
                        "stage": {"type": "string"},
                        "fact_ids": {"type": "array", "items": {"type": "string"}},
                        "overlay_rel": {"type": "string"},
                    },
                    "required": ["stage"],
                },
                kind="host",
                identity="rerun_stage",
            ),
            ToolSpec(
                name="walk_seed_remainder",
                description="Explicit catch-up: walk leftover seed-order stages. Not automatic.",
                parameters={
                    "type": "object",
                    "properties": {"reason": {"type": "string"}},
                },
                kind="host",
                identity="walk_seed_remainder",
            ),
            ToolSpec(
                name="invalidate_downstream",
                description=(
                    "Clear this stage and everything after (stale downstream). "
                    "Not a surgical rerun. Do not use for a single-stage QC miss "
                    "such as ideal_cuts span coverage — rerun_stage that stage instead."
                ),
                parameters={
                    "type": "object",
                    "properties": {"stage": {"type": "string"}},
                    "required": ["stage"],
                },
                kind="host",
                identity="invalidate_downstream",
            ),
            ToolSpec(
                name="axis_select",
                description="Choose source axes and fact IDs for the next packed volley.",
                parameters={
                    "type": "object",
                    "properties": {"tool_id": {"type": "string"}},
                    "required": ["tool_id"],
                },
                kind="host",
                identity="axis_select",
            ),
            ToolSpec(
                name="write_thinking",
                description="Append a tape-meaning note to the per-run knowledge base.",
                parameters={
                    "type": "object",
                    "properties": {"note": {"type": "string"}, "identity": {"type": "string"}},
                    "required": ["note"],
                },
                kind="host",
                identity="write_thinking",
            ),
            ToolSpec(
                name="build_source_card",
                description="Refresh source_card (topology, duration, islands) and admit it.",
                parameters={"type": "object", "properties": {}},
                kind="host",
                identity="build_source_card",
            ),
        ]
    )
    return specs


def operator_action_specs() -> list[ToolSpec]:
    path = repo_root() / "docs" / "cross-cutting" / "operator_action_catalog.json"
    if not path.is_file():
        return []
    import json

    rows = json.loads(path.read_text(encoding="utf-8"))
    specs: list[ToolSpec] = []
    if not isinstance(rows, list):
        return specs
    for row in rows:
        if not isinstance(row, dict):
            continue
        aid = str(row.get("action_id") or "")
        if not aid or "[REMOVED]" in str(row.get("description") or ""):
            continue
        slug = aid.replace(".", "_").replace("-", "_")
        specs.append(
            ToolSpec(
                name=f"gui_{slug}"[:64],
                description=str(row.get("description") or aid)[:512],
                parameters={"type": "object", "properties": {"action_id": {"type": "string"}}},
                kind="operator_action",
                identity=aid,
            )
        )
    return specs


def prompt_specs() -> list[ToolSpec]:
    root = repo_root() / "docs" / "prompts"
    specs: list[ToolSpec] = []
    if not root.is_dir():
        return specs
    for path in sorted(root.rglob("*.system.txt")):
        rel = str(path.relative_to(repo_root())).replace("\\", "/")
        name = "prompt_" + rel.replace("docs/prompts/", "").replace("/", "_").replace(
            ".system.txt", ""
        )
        name = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)[:64]
        specs.append(
            ToolSpec(
                name=name,
                description=f"Instruction prompt {rel}",
                parameters={"type": "object", "properties": {}},
                kind="prompt",
                identity=rel,
                nested_llm=True,
                prompt_rel=rel,
            )
        )
    return specs


def all_specs() -> list[ToolSpec]:
    return stage_tool_specs() + operator_action_specs() + prompt_specs()


def spec_by_name() -> dict[str, ToolSpec]:
    return {s.name: s for s in all_specs()}
