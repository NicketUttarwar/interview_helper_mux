"""Run one pipeline stage in an isolated process (keeps the web server responsive)."""

from __future__ import annotations

import sys
import traceback


def run_stage_worker(run_id: str, stage_id: str) -> int:
    from interview_mux.gui_job_reconcile import WRITE_APPROVAL_EXIT, pause_job_for_write_approval
    from interview_mux.run_context import RunContext
    from interview_mux.run_lock import run_directory_lock
    from interview_mux.write_staging import WriteApprovalPending

    with run_directory_lock(run_id):
        ctx = RunContext(run_id, create=False)
        from interview_mux.pipeline import run_single_stage

        try:
            run_single_stage(ctx, stage_id)
        except WriteApprovalPending as exc:
            pause_job_for_write_approval(ctx, exc)
            return WRITE_APPROVAL_EXIT
        except SystemExit as exc:
            msg = str(exc).strip() or f"Stage {stage_id} stopped"
            ctx.log(msg, level="error", stage=stage_id)
            return 1
        except Exception as exc:
            ctx.log(
                f"Stage {stage_id} failed: {exc}",
                level="error",
                stage=stage_id,
                detail=traceback.format_exc()[:2000],
            )
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) != 2:
        print("Usage: python -m interview_mux.stage_worker RUN_ID STAGE_ID", file=sys.stderr)
        return 2
    run_id, stage_id = args
    return run_stage_worker(run_id, stage_id)


if __name__ == "__main__":
    raise SystemExit(main())
