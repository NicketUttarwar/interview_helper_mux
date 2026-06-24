/**
 * Static sanity checks for operator button / CTA wiring across the GUI.
 * Run via: npm test -- buttonSanity
 */
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveOperatorAction, resolveOperatorActionForStage } from "./resolveOperatorAction";
import { substepShouldOpenModal } from "./substepModal";
import { invokeOperatorActionPrimary } from "./operatorActionHandlers";
import type { RunData, StageInfo, StageSubstep } from "../types";

const ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "..");

/** data-testid values referenced by CURSOR_EXECUTE/flow1-gui-e2e/driver/gate_handlers.py */
const E2E_CRITICAL_TESTIDS: Array<string | { pattern: RegExp; label: string }> = [
  "step-action-primary",
  "checkpoint-continue",
  "write-approval-save-continue",
  "live-status-primary",
  "handoff-acknowledge",
  "reuse-run-fresh",
  "complete-transcript-review",
  "complete-disfluency-review",
  "disfluency-confirm-all",
  "mark-profile-verified",
  "mark-profile-verified-modal",
  "vo-continue",
  { pattern: /select-flow-\$\{/, label: "select-flow (dynamic)" },
  "approve-sfx-prompts",
  "sfx-post-listen-pass-all",
  "operator-action-modal",
  "pending-action-primary",
  { pattern: /preclean-accept-\$\{/, label: "preclean-accept (dynamic)" },
  "start-tab-ready",
];

function collectSourceFiles(dir: string, acc: string[] = []): string[] {
  let st;
  try {
    st = statSync(dir);
  } catch {
    return acc;
  }
  if (!st.isDirectory()) return acc;
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist") continue;
    const path = join(dir, name);
    const st = statSync(path);
    if (st.isDirectory()) {
      collectSourceFiles(path, acc);
    } else if (/\.(tsx?|css)$/.test(name)) {
      acc.push(path);
    }
  }
  return acc;
}

function stage(id: string, status: StageInfo["status"], title = id): StageInfo {
  return { id, title, status, description: `${title} step` };
}

function baseRun(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_001_test",
    stages: [],
    journey: {
      phase: "prepare",
      milestones: {},
      next_action: "Continue",
    },
    ...overrides,
  } as RunData;
}

function collectComponentSources(): string {
  const dirs = ["components", "context", "hooks"].map((d) => join(ROOT, d));
  const files: string[] = [];
  for (const dir of dirs) {
    collectSourceFiles(dir, files);
  }
  return files.map((f) => readFileSync(f, "utf8")).join("\n");
}

describe("buttonSanity — E2E testid presence", () => {
  const corpus = collectComponentSources();

  it.each(
    E2E_CRITICAL_TESTIDS.map((entry) =>
      typeof entry === "string" ? [entry, entry] : [entry.label, entry.pattern],
    ),
  )("%s is declared in component source", (_label, needle) => {
    if (needle instanceof RegExp) {
      expect(corpus).toMatch(needle);
    } else {
      expect(corpus).toContain(`data-testid="${needle}"`);
    }
  });
});

describe("buttonSanity — no empty onClick handlers", () => {
  const tsxFiles = collectSourceFiles(join(ROOT, "components")).filter((f) => f.endsWith(".tsx"));

  it("no onClick={() => {}} no-ops in components", () => {
    const offenders: string[] = [];
    for (const file of tsxFiles) {
      const text = readFileSync(file, "utf8");
      if (/onClick=\{\(\) => \{\}\}/.test(text)) {
        offenders.push(relative(ROOT, file));
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("buttonSanity — operator primary actions are actionable", () => {
  const scenarios: Array<{
    name: string;
    run: RunData;
    stageId?: string;
    expectKind: string;
    expectPrimaryNotNone?: boolean;
  }> = [
    {
      name: "pending audio_preclean",
      run: baseRun({ stages: [stage("audio_preclean", "pending", "Audio pre-clean")] }),
      stageId: "audio_preclean",
      expectKind: "open_modal",
    },
    {
      name: "write approval ingest",
      run: baseRun({
        stages: [stage("ingest", "awaiting_write_approval", "Ingest")],
        job: {
          status: "awaiting_write_approval",
          pending_write_stage: "ingest",
          pending_write_paths: ["a.wav"],
        },
      }),
      expectKind: "open_modal",
    },
    {
      name: "next runnable ingest",
      run: baseRun({
        stages: [
          stage("audio_preclean", "done", "Pre-clean"),
          stage("ingest", "pending", "Ingest"),
        ],
      }),
      expectKind: "run_stage",
    },
    {
      name: "transcript review gate",
      run: baseRun({
        stages: [stage("transcript_review", "action_required", "Transcript review")],
        job: { status: "gate", stage: "transcript_review" },
      }),
      expectKind: "open_modal",
    },
    {
      name: "g2 flow select",
      run: baseRun({
        stages: [stage("g2_flow_select", "action_required", "Flow select")],
        job: { status: "gate", stage: "g2_flow_select" },
      }),
      stageId: "g2_flow_select",
      expectKind: "open_modal",
    },
    {
      name: "running job",
      run: baseRun({
        stages: [stage("ingest", "pending", "Ingest")],
        job: { status: "running", stage: "ingest", message: "Working" },
      }),
      expectKind: "none",
    },
    {
      name: "error job retry",
      run: baseRun({
        stages: [stage("transcribe", "pending", "Transcribe")],
        job: {
          status: "error",
          stage: "transcribe",
          last_error: { message: "failed", stage: "transcribe" },
        },
      }),
      expectKind: "run_stage",
    },
  ];

  it.each(scenarios)("$name resolves primaryKind=$expectKind", ({ run, stageId, expectKind }) => {
    const jobRunning = run.job?.status === "running" || run.job?.status === "running_with_warnings";
    const action = stageId
      ? resolveOperatorActionForStage(run, stageId, { jobRunning })
      : resolveOperatorAction(run, { jobRunning });
    expect(action.primaryKind).toBe(expectKind);
    if (expectKind !== "none") {
      expect(action.primaryLabel.length).toBeGreaterThan(0);
      if (expectKind !== "run_stage" || !jobRunning) {
        expect(action.primaryDisabled).toBe(false);
      }
    }
  });
});

describe("buttonSanity — invokeOperatorActionPrimary wiring", () => {
  it("open_modal calls openModal with stage and substep", () => {
    const calls: Array<{ sid?: string | null; subId?: string | null }> = [];
    invokeOperatorActionPrimary(
      {
        mode: "needs_you",
        stageId: "audio_preclean",
        substepId: "preclean:run",
        headline: "Run",
        subline: null,
        primaryLabel: "Run audio cleaning",
        primaryKind: "open_modal",
        primaryDisabled: false,
        modalAutoOpen: false,
        blockingReason: "preclean",
      },
      {
        openModal: (sid, subId) => calls.push({ sid, subId }),
        runStage: () => {},
        continueNext: () => {},
        viewLogs: () => {},
      },
    );
    expect(calls).toEqual([{ sid: "audio_preclean", subId: "preclean:run" }]);
  });

  it("run_stage calls runStage with stage id", () => {
    let ran: string | null = null;
    invokeOperatorActionPrimary(
      {
        mode: "idle",
        stageId: "ingest",
        substepId: null,
        headline: "Run",
        subline: null,
        primaryLabel: "Run Ingest",
        primaryKind: "run_stage",
        primaryDisabled: false,
        modalAutoOpen: false,
      },
      {
        openModal: () => {},
        runStage: (sid) => {
          ran = sid;
        },
        continueNext: () => {},
        viewLogs: () => {},
      },
    );
    expect(ran).toBe("ingest");
  });
});

describe("buttonSanity — substep modal policy", () => {
  function sub(partial: Partial<StageSubstep> & Pick<StageSubstep, "kind" | "stageId">): StageSubstep {
    return {
      id: partial.id ?? partial.kind,
      label: partial.label ?? partial.kind,
      status: partial.status ?? "todo",
      source: partial.source ?? "attention",
      ...partial,
    };
  }

  const modalCases: Array<[string, StageSubstep, boolean]> = [
    ["gate", sub({ kind: "gate", stageId: "g2_flow_select" }), true],
    ["checkpoint preclean", sub({ kind: "checkpoint", id: "preclean:run", stageId: "audio_preclean" }), true],
    ["write_approval", sub({ kind: "write_approval", stageId: "ingest" }), true],
    ["handoff", sub({ kind: "handoff", stageId: "topic_coverage_audit" }), true],
    ["reuse", sub({ kind: "reuse", stageId: "transcribe" }), true],
    ["profile nav", sub({ kind: "profile", stageId: "analysis_profile" }), false],
    ["optional skip", sub({ kind: "optional", id: "optional:skip", stageId: "audio_preclean" }), false],
    ["optional preclean review", sub({ kind: "optional", id: "optional:review", stageId: "g1_vo_pickup" }), true],
  ];

  it.each(modalCases)("%s → openModal=%s", (_label, substep, expected) => {
    expect(substepShouldOpenModal(substep)).toBe(expected);
  });
});

describe("buttonSanity — ModalHost mounts OperatorActionModal", () => {
  it("ModalHost imports and renders OperatorActionModal when actionModalOpen", () => {
    const text = readFileSync(join(ROOT, "components/modals/ModalHost.tsx"), "utf8");
    expect(text).toContain("OperatorActionModal");
    expect(text).toContain("actionModalOpen");
  });
});

describe("buttonSanity — AppContext openActionModal toggles modal state", () => {
  it("openActionModal sets actionModalOpen true", () => {
    const text = readFileSync(join(ROOT, "context/AppContext.tsx"), "utf8");
    expect(text).toMatch(/setActionModalOpen\(true\)/);
    expect(text).toMatch(/setActionModalOpen\(false\)/);
  });

  it("executeJob guards against duplicate runs", () => {
    const text = readFileSync(join(ROOT, "context/AppContext.tsx"), "utf8");
    expect(text).toContain("jobRunningRef.current");
    expect(text).toContain("actionBusyRef.current");
  });

  it("checkpoint continue bypasses actionBusy guard", () => {
    const text = readFileSync(join(ROOT, "context/AppContext.tsx"), "utf8");
    expect(text).toContain("checkpoint_continue");
    expect(text).toContain("advanceFromCheckpoint");
    expect(text).toContain("closeActionModalAfterSuccess");
  });
});

describe("buttonSanity — guardBusy helper", () => {
  it("guardBusy is exported and used by primary handlers", () => {
    const guardText = readFileSync(join(ROOT, "utils/guardBusy.ts"), "utf8");
    expect(guardText).toContain("export function guardBusy");
    const stageDetail = readFileSync(join(ROOT, "components/workspace/StageDetail.tsx"), "utf8");
    expect(stageDetail).toContain("guardBusy");
    expect(stageDetail).toContain("guardPrimary");
  });
});

describe("buttonSanity — analysis profile checkpoint", () => {
  it("shared helper is used by gate, profile, and story panels", () => {
    for (const rel of [
      "components/gates/AnalysisProfileGate.tsx",
      "components/workspace/ProfilePanel.tsx",
      "components/workspace/StoryBoardPanel.tsx",
    ]) {
      const text = readFileSync(join(ROOT, rel), "utf8");
      expect(text).toContain("completeAnalysisProfile");
    }
  });
});

describe("buttonSanity — holistic feedback hooks", () => {
  it("useAsyncAction is used by handoff and preview listen panels", () => {
    for (const rel of [
      "components/workspace/HandoffPanel.tsx",
      "components/guidance/PreviewListenPromo.tsx",
    ]) {
      const text = readFileSync(join(ROOT, rel), "utf8");
      expect(text).toContain("useAsyncAction");
    }
  });

  it("jobCompletionHint is wired in AppContext", () => {
    const text = readFileSync(join(ROOT, "context/AppContext.tsx"), "utf8");
    expect(text).toContain("jobCompletionHint");
  });

  it("secondary panels use async feedback patterns", () => {
    const artifact = readFileSync(join(ROOT, "components/workspace/ArtifactEditor.tsx"), "utf8");
    expect(artifact).toContain("saving");
    expect(artifact).toContain("spinner-inline");
    const deliverable = readFileSync(join(ROOT, "components/workspace/DeliverableCard.tsx"), "utf8");
    expect(deliverable).toContain("useAsyncAction");
    const timeline = readFileSync(join(ROOT, "hooks/useTimelineEditor.ts"), "utf8");
    expect(timeline).toContain("Timeline updated");
  });
});
