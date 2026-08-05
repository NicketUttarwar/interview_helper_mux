"""Registry of run-scoped mutating API routes that must hold operator_guard."""

from __future__ import annotations

# POST/PUT/PATCH/DELETE under /api/runs/{run_id}/ that write run disk state.
# Read-only or session-global routes are excluded.
GUARDED_RUN_ROUTE_KEYS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/runs/{run_id}/recompute-acoustic-profile"),
        ("PUT", "/api/runs/{run_id}/nle"),
        ("PATCH", "/api/runs/{run_id}/nle/segment"),
        ("POST", "/api/runs/{run_id}/nle/split"),
        ("POST", "/api/runs/{run_id}/nle/batch"),
        ("POST", "/api/runs/{run_id}/nle/snap-boundary"),
        ("PUT", "/api/runs/{run_id}/llm-calls/record"),
        ("POST", "/api/runs/{run_id}/context-index/entries"),
        ("PUT", "/api/runs/{run_id}/context-index/entries/{entry_id}"),
        ("POST", "/api/runs/{run_id}/context-index/entries/{entry_id}/invalidate"),
        ("POST", "/api/runs/{run_id}/context-index/rebuild"),
        ("PUT", "/api/runs/{run_id}/artifact/text"),
        ("PUT", "/api/runs/{run_id}/artifact"),
        ("POST", "/api/runs/{run_id}/preclean-offer"),
        ("POST", "/api/runs/{run_id}/stages/{stage_id}/reuse"),
        ("PUT", "/api/runs/{run_id}/sfx-prompts"),
        ("POST", "/api/runs/{run_id}/sfx-prompts/approve"),
        ("POST", "/api/runs/{run_id}/sfx-prompts/listen-result"),
        ("POST", "/api/runs/{run_id}/sfx-prompts/refine"),
        ("POST", "/api/runs/{run_id}/sfx-prompts/regenerate"),
        ("POST", "/api/runs/{run_id}/execute"),
        ("POST", "/api/runs/{run_id}/fill-artifact-gaps"),
        ("POST", "/api/runs/{run_id}/extract-value-features"),
        ("PATCH", "/api/runs/{run_id}/transcript/words"),
        ("PUT", "/api/runs/{run_id}/transcript/text"),
        ("POST", "/api/runs/{run_id}/transcript/reuse-edit/complete"),
        ("POST", "/api/runs/{run_id}/transcript/reuse-edit/dismiss"),
        ("PUT", "/api/runs/{run_id}/transcript-review/{chunk_id}"),
        ("PUT", "/api/runs/{run_id}/analysis-profile"),
        ("POST", "/api/runs/{run_id}/analysis-profile/verify"),
        ("PATCH", "/api/runs/{run_id}/investigation-queue/{item_id}"),
        ("POST", "/api/runs/{run_id}/milestones/preview-listened"),
        ("POST", "/api/runs/{run_id}/transcript-review/complete"),
        ("POST", "/api/runs/{run_id}/vo/{line_id}"),
        ("POST", "/api/runs/{run_id}/vo/{line_id}/synthesize"),
        ("POST", "/api/runs/{run_id}/vo/{line_id}/match"),
        ("POST", "/api/runs/{run_id}/vo/{line_id}/tone"),
        ("POST", "/api/runs/{run_id}/g1/skip-optional"),
        ("POST", "/api/runs/{run_id}/g1/synthesize-all"),
        ("PATCH", "/api/runs/{run_id}/delivery-brief"),
        ("POST", "/api/runs/{run_id}/delivery-brief/rebuild"),
        ("PATCH", "/api/runs/{run_id}/flow-adaptation"),
        ("POST", "/api/runs/{run_id}/flow-adaptation/confirm"),
        ("POST", "/api/runs/{run_id}/speaker-roles/confirm-hypothesis"),
        ("PATCH", "/api/runs/{run_id}/pickup-speaker"),
        ("POST", "/api/runs/{run_id}/pickup-speaker/confirm"),
        ("POST", "/api/runs/{run_id}/gap-framing/enable"),
        ("POST", "/api/runs/{run_id}/gap-framing/delivery"),
        ("PATCH", "/api/runs/{run_id}/voice-reference/select"),
        ("POST", "/api/runs/{run_id}/voice-reference/approve"),
        ("POST", "/api/runs/{run_id}/voice-clone-consent"),
        ("DELETE", "/api/runs/{run_id}/voice-clone-consent"),
        ("POST", "/api/runs/{run_id}/gap-fill/skip"),
        ("POST", "/api/runs/{run_id}/gap-report/lines"),
        ("PATCH", "/api/runs/{run_id}/gap-report/lines/{line_id}"),
        ("DELETE", "/api/runs/{run_id}/gap-report/lines/{line_id}"),
        ("POST", "/api/runs/{run_id}/vo/{line_id}/trim"),
        ("POST", "/api/runs/{run_id}/reset"),
        ("POST", "/api/runs/{run_id}/recompute-interview-spine"),
        ("POST", "/api/runs/{run_id}/recompute-coherence"),
        ("PATCH", "/api/runs/{run_id}/acoustic-profile/overrides"),
        ("PATCH", "/api/runs/{run_id}/soundscape-policy/overrides"),
        ("POST", "/api/runs/{run_id}/action-trace/dump-last"),
        ("POST", "/api/runs/{run_id}/reuse-from-previous"),
        ("POST", "/api/runs/{run_id}/g-listen/continue"),
        ("POST", "/api/runs/{run_id}/g-listen/skip"),
        ("POST", "/api/runs/{run_id}/g-publish/continue"),
        ("POST", "/api/runs/{run_id}/g-publish/skip"),
        ("POST", "/api/runs/{run_id}/g-publish/sync"),
        ("POST", "/api/runs/{run_id}/music-listen/approve"),
        ("POST", "/api/runs/{run_id}/timeline-optimizer/start"),
        ("POST", "/api/runs/{run_id}/timeline-optimizer/stop"),
        ("POST", "/api/runs/{run_id}/timeline-optimizer/skip"),
        ("POST", "/api/runs/{run_id}/timeline-optimizer/take-best"),
    }
)

# Mutating routes that only read/search — no disk write, guard optional.
GUARD_EXEMPT_RUN_ROUTE_KEYS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/runs/{run_id}/interview-spine/query"),
        ("POST", "/api/runs/{run_id}/log"),
    }
)

__all__ = ["GUARDED_RUN_ROUTE_KEYS", "GUARD_EXEMPT_RUN_ROUTE_KEYS"]
