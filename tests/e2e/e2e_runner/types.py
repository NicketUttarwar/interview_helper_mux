"""Shared types for E2E runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


FlowName = str  # flow1 | flow2 | flow3


class StepKind(str, Enum):
    WAIT = "wait"
    EXECUTE = "execute"
    RESOLVE_GATE = "resolve_gate"
    VERIFY_FLOW = "verify_flow"
    DONE = "done"


@dataclass
class StepAction:
    kind: StepKind
    detail: str = ""
    execute_body: dict[str, Any] | None = None


@dataclass
class SessionConfig:
    repo_root: str
    input_audio: str = "ASSETS/input/interview.wav"
    flows: tuple[FlowName, ...] = ("flow1", "flow2", "flow3")
    base_url: str = "http://127.0.0.1:8765"
    poll_interval_s: float = 2.0
    heal_enabled: bool = True
    max_heal_attempts: int = 5
    resume_run_id: str | None = None
    until_stage: str | None = None
    headless: bool = True
    log_dir: str = ""


@dataclass
class IncidentRecord:
    incident_id: int
    timestamp: str
    elapsed_s: float
    failure_type: str
    summary: str
    run_id: str | None
    flow: str | None
    phase: str | None
    next_action: str | None
    stage_id: str | None
    symptom: str
    root_cause: str = ""
    severity: str = "major"
    fix_applied: str = ""
    files_changed: list[str] = field(default_factory=list)
    verification: str = ""
    bundle_path: str = ""
    heal_transcript_path: str = ""
