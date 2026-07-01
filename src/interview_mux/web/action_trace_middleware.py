"""FastAPI middleware — begin/end action trace for mutating run API calls."""

from __future__ import annotations

import re
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_ROUTE_ACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^/api/runs/[^/]+/stages/[^/]+/decisions/[^/]+/resolve$"), "api.decision.resolve"),
    (re.compile(r"^/api/runs/[^/]+/stages/[^/]+/issues/auto-resolve$"), "api.itr.auto_resolve"),
    (re.compile(r"^/api/runs/[^/]+/stages/[^/]+/issues/revalidate$"), "api.itr.revalidate"),
    (re.compile(r"^/api/runs/[^/]+/stages/[^/]+/propagation/execute$"), "api.itr.propagation"),
    (re.compile(r"^/api/runs/[^/]+/stages/[^/]+/issues/[^/]+/resolve$"), "api.itr.issue_resolve"),
    (re.compile(r"^/api/runs/[^/]+/execute$"), "api.pipeline.execute"),
    (re.compile(r"^/api/runs/[^/]+/continue-after-checkpoint$"), "api.write_approval.continue"),
    (re.compile(r"^/api/runs/[^/]+/pending-writes/[^/]+/approve$"), "api.write_approval.approve"),
    (re.compile(r"^/api/runs/[^/]+/pending-writes/[^/]+/discard$"), "api.write_approval.discard"),
    (re.compile(r"^/api/runs/[^/]+/handoff-ack$"), "api.handoff.acknowledge"),
    (re.compile(r"^/api/runs/[^/]+/stages/[^/]+/reuse$"), "api.stage_reuse.decide"),
    (re.compile(r"^/api/runs/[^/]+/preclean-offer$"), "api.preclean.offer"),
    (re.compile(r"^/api/runs/[^/]+/log$"), "api.log.append"),
    (re.compile(r"^/api/runs/[^/]+/action-trace/dump-last$"), "gui.activity.dump_last"),
    (re.compile(r"^/api/runs/[^/]+/"), "api.run.mutate"),
]


def _action_for_path(path: str, method: str) -> str | None:
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    for pat, aid in _ROUTE_ACTIONS:
        if pat.search(path):
            return aid
    return None


def _run_id_from_path(path: str) -> str | None:
    m = re.match(r"^/api/runs/([^/]+)", path)
    return m.group(1) if m else None


class ActionTraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        action_id = _action_for_path(path, request.method)
        run_id = _run_id_from_path(path)
        trace_id = None
        if action_id and run_id:
            try:
                from interview_mux.operator_action_trace import begin_action, end_action
                from interview_mux.run_context import RunContext

                ctx = RunContext(run_id, create=False)
                trace_id = begin_action(
                    action_id,
                    run_dir=ctx.run_dir,
                    origin="api",
                    http={"method": request.method, "path": path},
                )
            except Exception:
                trace_id = None
        try:
            response = await call_next(request)
            if trace_id and run_id:
                from interview_mux.operator_action_trace import end_action
                from interview_mux.run_context import RunContext

                ctx = RunContext(run_id, create=False)
                status = "ok" if response.status_code < 400 else "error"
                end_action(trace_id, run_dir=ctx.run_dir, status=status)
            return response
        except Exception:
            if trace_id and run_id:
                from interview_mux.operator_action_trace import end_action
                from interview_mux.run_context import RunContext

                ctx = RunContext(run_id, create=False)
                end_action(trace_id, run_dir=ctx.run_dir, status="error")
            raise
