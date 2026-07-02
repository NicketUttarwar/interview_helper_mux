#!/usr/bin/env python3
"""Audit operator subprocess usage and checkpoint-continuation wiring."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = ROOT / "src" / "interview_mux" / "stages"
FRONTEND = ROOT / "frontend" / "src"

ALLOWED = {
    ROOT / "src" / "interview_mux" / "operator_subprocess.py",
    ROOT / "src" / "interview_mux" / "local_runtime.py",
    ROOT / "src" / "interview_mux" / "local_llm_selection.py",
    ROOT / "src" / "interview_mux" / "hardware_detect.py",
}

PAT = re.compile(r"subprocess\.(run|Popen)\(")

CHECKPOINT_CONTINUATION = [
    ("context/AppContext.tsx", "advanceFromCheckpoint"),
    ("context/AppContext.tsx", "completeTranscriptReview"),
    ("context/AppContext.tsx", "approveSfxPrompts"),
    ("context/AppContext.tsx", "approveWriteAndContinue"),
    ("context/AppContext.tsx", "acknowledgeHandoff"),
    ("context/AppContext.tsx", "reconcileBusyRun"),
    ("context/AppContext.tsx", "checkpoint_continue"),
    ("utils/checkpointContinuation.ts", "advancePipeline"),
    ("utils/checkpointContinuation.ts", "reconcileBusyRun"),
    ("components/workspace/StageStepFooter.tsx", "advanceFromCheckpoint"),
    ("components/gates/StageReviewGateBanner.tsx", "approveWriteAndContinue"),
    ("components/guidance/WriteApprovalPanel.tsx", "Save all files &amp; continue"),
    ("components/guidance/StageReuseOfferCard.tsx", "applyReuseResultAndFocus"),
    ("components/gates/DisfluencyReviewPanel.tsx", "advanceFromCheckpoint"),
    ("components/gates/VoPickupPanel.tsx", "advanceFromCheckpoint"),
    ("components/gates/FlowSelectPanel.tsx", "advanceFromCheckpoint"),
    ("components/gates/AnalysisProfileGate.tsx", "advanceFromCheckpoint"),
    ("components/gates/SfxPostListenPanel.tsx", "advanceFromCheckpoint"),
    ("components/gates/PickupSpeakerPanel.tsx", "advanceFromCheckpoint"),
    ("components/gates/PreviewPickupPanel.tsx", "advanceFromCheckpoint"),
    ("components/gates/PrecleanOfferCard.tsx", "beginStageExecution"),
]

BACKEND_CHECKPOINT = [
    ("src/interview_mux/web/server.py", "continue-after-checkpoint"),
    ("src/interview_mux/web/server.py", "run_in_threadpool"),
    ("src/interview_mux/write_staging.py", "write_approval.flush"),
    ("src/interview_mux/ui_truth.py", "T10"),
]


def audit_subprocess() -> list[str]:
    bad: list[str] = []
    for path in STAGES.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if PAT.search(text):
            bad.append(str(path.relative_to(ROOT)))
    return bad


def audit_checkpoint_continuation() -> list[str]:
    missing: list[str] = []
    for rel, needle in CHECKPOINT_CONTINUATION:
        path = FRONTEND / rel
        if not path.is_file():
            missing.append(f"missing file: {rel}")
            continue
        if needle not in path.read_text(encoding="utf-8"):
            missing.append(f"{rel}: expected {needle!r}")
    for rel, needle in BACKEND_CHECKPOINT:
        path = ROOT / rel
        if not path.is_file():
            missing.append(f"missing file: {rel}")
            continue
        if needle not in path.read_text(encoding="utf-8"):
            missing.append(f"{rel}: expected {needle!r}")
    return missing


def main() -> int:
    errors: list[str] = []
    subprocess_bad = audit_subprocess()
    if subprocess_bad:
        errors.append("Stages must use operator_subprocess.run_command, not raw subprocess:")
        errors.extend(f"  - {b}" for b in subprocess_bad)

    checkpoint_missing = audit_checkpoint_continuation()
    if checkpoint_missing:
        errors.append("Checkpoint continuation checklist failures:")
        errors.extend(f"  - {m}" for m in checkpoint_missing)

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print("OK — subprocess audit + checkpoint continuation checklist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
