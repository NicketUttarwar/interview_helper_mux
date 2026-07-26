import type {
  AppConfig,
  JourneyState,
  LogEntry,
  LogLevel,
  RunData,
  StageGuidance,
  StageInfo,
  StageStep,
  TimelineData,
} from "../types";

/** StageInfo with only the fields a test cares about; the rest get safe defaults. */
export function makeStage(
  id: string,
  overrides: Partial<StageInfo> = {},
): StageInfo {
  return {
    id,
    title: id,
    description: "",
    status: "pending",
    ...overrides,
  };
}

/** JourneyState with the required spine fields filled in. */
export function makeJourney(overrides: Partial<JourneyState> = {}): JourneyState {
  return {
    phase: "prepare",
    milestones: {},
    next_action: "",
    blocking: {},
    ...overrides,
  };
}

/** Numbered workbench step with the required copy fields filled in. */
export function makeStep(id: string, overrides: Partial<StageStep> = {}): StageStep {
  return {
    id,
    number: 1,
    label: id,
    instruction: "",
    review: [],
    kind: "run",
    status: "todo",
    ...overrides,
  };
}

/** StageGuidance with the required copy fields filled in. */
export function makeGuidance(overrides: Partial<StageGuidance> = {}): StageGuidance {
  return {
    phase_label: "",
    prerequisites: [],
    actions: [],
    unlocks: "",
    ...overrides,
  };
}

/** AppConfig with the required roots filled in so tests can pass just journey_ui. */
export function makeConfig(overrides: Partial<AppConfig> = {}): AppConfig {
  return {
    assets_root: "/tmp/assets",
    executions_root: "/tmp/assets/executions",
    data_root: "/tmp/data",
    web_port: 8000,
    repo_root: "/tmp/repo",
    ...overrides,
  };
}

/** Minimal run payload for navigation / availability matrix tests. */
export function makeRunFixture(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_test_fixture",
    stages: [
      makeStage("ingest", { title: "Ingest", status: "done" }),
      makeStage("content_context", { title: "Content", status: "pending" }),
      makeStage("segment_classification", { title: "Classify", status: "pending" }),
      makeStage("narrative_arc_plan", { title: "Narrative arc", status: "locked" }),
    ],
    ...overrides,
  };
}

export function makeTimelineFixture(segments = 0): TimelineData {
  return {
    segments: Array.from({ length: segments }, (_, i) => ({
      segment_id: `seg_${i}`,
      start_ms: i * 1000,
      end_ms: (i + 1) * 1000,
      text: "sample",
    })),
    duration_ms: segments * 1000,
    vo_lines: [],
    nle: null,
  };
}

export function makeLogEntry(
  message: string,
  level: LogLevel = "info",
  ts = "2026-06-22T12:00:00.000Z",
): LogEntry {
  return { ts, message, level };
}
