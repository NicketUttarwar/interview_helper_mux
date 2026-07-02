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
        ("POST", "/api/runs/{run_id}/flow"),
        ("POST", "/api/runs/{run_id}/preclean-offer"),
        ("PUT", "/api/runs/{run_id}/pending-writes/{stage_id}/content"),
        ("POST", "/api/runs/{run_id}/pending-writes/{stage_id}/approve"),
        ("POST", "/api/runs/{run_id}/continue-after-checkpoint"),
        ("POST", "/api/runs/{run_id}/pending-writes/{stage_id}/discard"),
        ("POST", "/api/runs/{run_id}/stages/{stage_id}/issues/auto-resolve"),
        ("POST", "/api/runs/{run_id}/stages/{stage_id}/issues/auto-repair"),
        ("POST", "/api/runs/{run_id}/stages/{stage_id}/issues/{issue_id}/resolve"),
        ("POST", "/api/runs/{run_id}/stages/{stage_id}/issues/revalidate"),
        ("POST", "/api/runs/{run_id}/stages/{stage_id}/decisions/{decision_id}/resolve"),
        ("POST", "/api/runs/{run_id}/stages/{stage_id}/propagation/execute"),
        ("POST", "/api/runs/{run_id}/stages/{stage_id}/issues/{issue_id}/execute-action"),
        ("POST", "/api/runs/{run_id}/stages/{stage_id}/reuse"),
        ("PUT", "/api/runs/{run_id}/sfx-prompts"),
        ("POST", "/api/runs/{run_id}/sfx-prompts/approve"),
        ("POST", "/api/runs/{run_id}/sfx-prompts/listen-result"),
        ("POST", "/api/runs/{run_id}/sfx-prompts/refine"),
        ("POST", "/api/runs/{run_id}/sfx-prompts/regenerate"),
        ("POST", "/api/runs/{run_id}/handoff-ack"),
        ("POST", "/api/runs/{run_id}/execute"),
        ("POST", "/api/runs/{run_id}/fill-artifact-gaps"),
        ("POST", "/api/runs/{run_id}/extract-value-features"),
        ("PATCH", "/api/runs/{run_id}/transcript/words"),
        ("PUT", "/api/runs/{run_id}/transcript-review/{chunk_id}"),
        ("PUT", "/api/runs/{run_id}/analysis-profile"),
        ("POST", "/api/runs/{run_id}/analysis-profile/verify"),
        ("PATCH", "/api/runs/{run_id}/investigation-queue/{item_id}"),
        ("POST", "/api/runs/{run_id}/milestones/preview-listened"),
        ("POST", "/api/runs/{run_id}/transcript-review/complete"),
        ("PUT", "/api/runs/{run_id}/disfluency-review/{event_id}"),
        ("POST", "/api/runs/{run_id}/disfluency-review/complete"),
        ("PATCH", "/api/runs/{run_id}/disfluency-restore"),
        ("POST", "/api/runs/{run_id}/vo/{line_id}"),
        ("PATCH", "/api/runs/{run_id}/flow-adaptation"),
        ("POST", "/api/runs/{run_id}/flow-adaptation/confirm"),
        ("PATCH", "/api/runs/{run_id}/pickup-speaker"),
        ("POST", "/api/runs/{run_id}/pickup-speaker/confirm"),
        ("POST", "/api/runs/{run_id}/gap-report/lines"),
        ("PATCH", "/api/runs/{run_id}/gap-report/lines/{line_id}"),
        ("DELETE", "/api/runs/{run_id}/gap-report/lines/{line_id}"),
        ("POST", "/api/runs/{run_id}/vo/{line_id}/trim"),
        ("POST", "/api/runs/{run_id}/reset"),
        ("POST", "/api/runs/{run_id}/recompute-interview-spine"),
        ("POST", "/api/runs/{run_id}/recompute-coherence"),
        ("PATCH", "/api/runs/{run_id}/acoustic-profile/overrides"),
        ("POST", "/api/runs/{run_id}/log"),
        ("POST", "/api/runs/{run_id}/action-trace/dump-last"),
        ("POST", "/api/runs/{run_id}/reuse-from-previous"),
    }
)

# Mutating routes that only read/search — no disk write, guard optional.
GUARD_EXEMPT_RUN_ROUTE_KEYS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/runs/{run_id}/interview-spine/query"),
    }
)

__all__ = ["GUARDED_RUN_ROUTE_KEYS", "GUARD_EXEMPT_RUN_ROUTE_KEYS"]
