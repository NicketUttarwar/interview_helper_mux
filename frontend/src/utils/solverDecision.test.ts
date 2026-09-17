import { describe, expect, it } from "vitest";
import {
  buildSolverPanelModel,
  describeReason,
  describeUnknown,
  resolveHaltKind,
  type SolverDecisionRow,
  type SolverDecisionView,
} from "./solverDecision";

function row(overrides: Partial<SolverDecisionRow> = {}): SolverDecisionRow {
  return {
    at: "2026-09-16T12:00:00Z",
    posture: "manual",
    lease_ok: true,
    admissible: [],
    would_choose: null,
    would_choose_confident: null,
    deferred: [],
    seed_first_incomplete: null,
    halted: true,
    excluded: [],
    admissible_detail: [],
    ...overrides,
  };
}

function view(overrides: Partial<SolverDecisionView> = {}): SolverDecisionView {
  return {
    artifact: "operator/solver_decision.jsonl",
    authoritative: false,
    shadow_logging: false,
    writable: true,
    ownership_row_registered: false,
    rows: [],
    live: null,
    halt: null,
    ...overrides,
  };
}

describe("empty telemetry", () => {
  it("renders as no_data when the response is missing entirely", () => {
    const model = buildSolverPanelModel(null);
    expect(model.state).toBe("no_data");
    expect(model.source).toBeNull();
    expect(model.blocked).toEqual([]);
  });

  it("renders as no_data when the log is absent and the live row says nothing", () => {
    const model = buildSolverPanelModel(view());
    expect(model.state).toBe("no_data");
    expect(model.loggedRowCount).toBe(0);
    expect(model.shadowOnly).toBe(true);
  });

  it("never reports a halt from a contentless live row", () => {
    const model = buildSolverPanelModel(view({ live: row({ halted: true }) }));
    expect(model.state).toBe("no_data");
  });

  it("falls back to the newest logged row when the live row is empty", () => {
    const model = buildSolverPanelModel(
      view({
        live: row(),
        rows: [
          row({ at: "older", admissible: ["ingest"], halted: false }),
          row({ at: "newest", admissible: ["transcribe"], halted: false }),
        ],
      }),
    );
    expect(model.source).toBe("logged");
    expect(model.at).toBe("newest");
    expect(model.runnable).toEqual(["transcribe"]);
  });
});

describe("blocked stages", () => {
  const halted = view({
    live: row({
      halted: true,
      excluded: [
        {
          stage: "speaker_roles",
          admissible: false,
          phase: "understand-a",
          reason: "hard_input_missing:understanding/interview_spine.json",
          reasons: ["hard_input_missing:understanding/interview_spine.json"],
          confident: true,
          detail: {
            producers: {
              "understanding/interview_spine.json": "interview_spine_build",
            },
          },
        },
        {
          stage: "content_context",
          admissible: false,
          phase: "understand-a",
          reason: "hard_input_missing:understanding/interview_spine.json",
          reasons: [
            "hard_input_missing:understanding/interview_spine.json",
            "gate_open:transcript_review",
          ],
          confident: true,
          detail: {
            producers: {
              "understanding/interview_spine.json": "interview_spine_build",
            },
          },
        },
        {
          stage: "ingest",
          admissible: false,
          phase: "prepare",
          reason: "already_done",
          reasons: ["already_done"],
          confident: true,
        },
      ],
    }),
  });

  it("names the reason and the producer that would satisfy it", () => {
    const model = buildSolverPanelModel(halted);
    expect(model.state).toBe("halted");
    const blocked = model.blocked.find((b) => b.stage === "speaker_roles");
    expect(blocked?.kind).toBe("input");
    expect(blocked?.artifact).toBe("understanding/interview_spine.json");
    expect(blocked?.producer).toBe("interview_spine_build");
    expect(blocked?.headline).toContain("has not been produced");
  });

  it("groups stages sharing one reason and keeps the secondary reasons", () => {
    const model = buildSolverPanelModel(halted);
    expect(model.blockedGroups).toHaveLength(1);
    expect(model.blockedGroups[0].stages).toEqual(["speaker_roles", "content_context"]);
    expect(model.blocked.find((b) => b.stage === "content_context")?.alsoBlockedBy).toEqual([
      "gate_open:transcript_review",
    ]);
  });

  it("does not count a finished stage as a blocker", () => {
    const model = buildSolverPanelModel(halted);
    expect(model.blocked.map((b) => b.stage)).not.toContain("ingest");
    expect(model.doneStages).toEqual(["ingest"]);
  });

  it("reads producers from the halt payload when the verdict omits them", () => {
    const model = buildSolverPanelModel(
      view({
        live: row({
          excluded: [
            {
              stage: "edl",
              admissible: false,
              reason: "hard_input_uncommitted:delivery/selection.json",
              reasons: ["hard_input_uncommitted:delivery/selection.json"],
            },
          ],
        }),
        halt: {
          halted: true,
          blockers: [
            {
              stage: "edl",
              producers: { "delivery/selection.json": "full_master_ranking" },
            },
          ],
        },
      }),
    );
    expect(model.blocked[0].producer).toBe("full_master_ranking");
  });

  it("treats an all-done run as complete rather than halted", () => {
    const model = buildSolverPanelModel(
      view({
        live: row({
          halted: true,
          excluded: [
            { stage: "ingest", admissible: false, reason: "already_done", reasons: ["already_done"] },
          ],
        }),
      }),
    );
    expect(model.state).toBe("complete");
  });
});

describe("deferred is not blocked", () => {
  const deferredView = view({
    live: row({
      halted: false,
      admissible: ["transitions", "edl"],
      would_choose: "transitions",
      would_choose_confident: "edl",
      deferred: ["transitions"],
      admissible_detail: [
        {
          stage: "transitions",
          admissible: true,
          phase: "plan_rank",
          confident: false,
          unknowns: ["hard_inputs_undeclared"],
        },
        { stage: "edl", admissible: true, phase: "build", confident: true },
      ],
    }),
  });

  it("keeps deferrals out of the blocked list", () => {
    const model = buildSolverPanelModel(deferredView);
    expect(model.state).toBe("moving");
    expect(model.blocked).toEqual([]);
    expect(model.deferred.map((d) => d.stage)).toEqual(["transitions"]);
  });

  it("explains a deferral as the solver having no opinion", () => {
    const model = buildSolverPanelModel(deferredView);
    expect(model.deferred[0].why).toContain("declares no hard inputs");
    expect(model.deferred[0].codes).toEqual(["hard_inputs_undeclared"]);
  });

  it("separates provable admissibility from deferred admissibility", () => {
    const model = buildSolverPanelModel(deferredView);
    expect(model.runnable).toEqual(["transitions", "edl"]);
    expect(model.confidentRunnable).toEqual(["edl"]);
  });
});

describe("lease pause vs structural halt", () => {
  const leaseExclusions = [
    {
      stage: "speaker_roles",
      admissible: false,
      phase: "understand-a",
      reason: "lease_held_by_gui",
      reasons: ["lease_held_by_gui"],
      confident: true,
    },
    {
      stage: "content_context",
      admissible: false,
      phase: "understand-a",
      reason: "lease_held_by_gui",
      reasons: ["lease_held_by_gui"],
      confident: true,
    },
  ];

  it("reads a lease_pause row as paused, with the waiting stages", () => {
    const model = buildSolverPanelModel(
      view({
        live: row({
          halted: true,
          paused: true,
          halt_kind: "lease_pause",
          lease_ok: false,
          excluded: leaseExclusions,
        }),
      }),
    );
    expect(model.state).toBe("paused");
    expect(model.haltKind).toBe("lease_pause");
    expect(model.paused).toBe(true);
    expect(model.haltReasonCode).toBe("lease_held_by_gui");
    expect(model.waiting).toEqual(["speaker_roles", "content_context"]);
    // The lease is a run-level wait, not sixty blockers to chase.
    expect(model.blocked).toEqual([]);
    expect(model.blockedGroups).toEqual([]);
  });

  it("reads a structural_halt row as halted and keeps its blockers", () => {
    const model = buildSolverPanelModel(
      view({
        live: row({
          halted: true,
          paused: false,
          halt_kind: "structural_halt",
          lease_ok: true,
          excluded: [
            {
              stage: "edl",
              admissible: false,
              reason: "hard_input_missing:delivery/selection.json",
              reasons: ["hard_input_missing:delivery/selection.json"],
            },
          ],
        }),
      }),
    );
    expect(model.state).toBe("halted");
    expect(model.haltKind).toBe("structural_halt");
    expect(model.paused).toBe(false);
    expect(model.haltReasonCode).toBe("");
    expect(model.waiting).toEqual([]);
    expect(model.blocked.map((b) => b.stage)).toEqual(["edl"]);
  });

  it("leaves a moving row with no halt kind at all", () => {
    const model = buildSolverPanelModel(
      view({ live: row({ halted: false, halt_kind: "", admissible: ["transcribe"] }) }),
    );
    expect(model.state).toBe("moving");
    expect(model.haltKind).toBe("");
    expect(model.paused).toBe(false);
  });

  it("renders a pause row that carries no verdicts, rather than calling it no_data", () => {
    // `_log_authoritative_pause` persists a decision with an empty verdict tuple.
    const model = buildSolverPanelModel(
      view({
        live: row({ halted: true, paused: true, halt_kind: "lease_pause", lease_ok: false }),
      }),
    );
    expect(model.state).toBe("paused");
    expect(model.waiting).toEqual([]);
  });

  it("treats a legacy row without halt_kind as a structural halt, not a pause", () => {
    // Rows predating 84b79344 carry lease_ok but no halt_kind. Calling a real halt a
    // pause would hide a stuck pipeline, so the missing field degrades to today's alarm.
    const legacy = row({
      halted: true,
      lease_ok: false,
      excluded: leaseExclusions,
    });
    delete legacy.halt_kind;
    delete legacy.paused;
    const model = buildSolverPanelModel(view({ live: legacy }));
    expect(model.state).toBe("halted");
    expect(model.haltKind).toBe("structural_halt");
    expect(model.paused).toBe(false);
    expect(model.waiting).toEqual([]);
    expect(model.blockedGroups[0].kind).toBe("lease");
  });

  it("does not upgrade an unrecognised halt_kind into a pause", () => {
    const model = buildSolverPanelModel(
      view({ live: row({ halted: true, halt_kind: "something_new", excluded: leaseExclusions }) }),
    );
    expect(model.state).toBe("halted");
    expect(model.haltKind).toBe("structural_halt");
  });

  it("resolves the halt kind of a row on its own", () => {
    expect(resolveHaltKind(null)).toBe("");
    expect(resolveHaltKind(row({ halted: false, admissible: ["ingest"] }))).toBe("");
    expect(resolveHaltKind(row({ halt_kind: "lease_pause" }))).toBe("lease_pause");
    expect(resolveHaltKind(row({ halt_kind: "structural_halt" }))).toBe("structural_halt");
    expect(resolveHaltKind(row({}))).toBe("structural_halt");
    // An admissible stage outranks a stale stamp: there is something to run.
    expect(
      resolveHaltKind(row({ halted: false, admissible: ["ingest"], halt_kind: "lease_pause" })),
    ).toBe("");
  });
});

describe("severed reachability", () => {
  it("surfaces the unmet dependency, producer and resume stage", () => {
    const model = buildSolverPanelModel(
      view({
        live: row({ halted: true }),
        halt: {
          reason: "master.wav unreachable",
          resume: "full_master_ranking",
          unmet: [
            {
              artifact: "delivery/selection.json",
              required_by: "edl",
              producers: ["full_master_ranking"],
              blocker: "artifact quarantined",
              resume: "full_master_ranking",
            },
          ],
        },
      }),
    );
    expect(model.severed?.resume).toBe("full_master_ranking");
    expect(model.severed?.unmet[0]).toMatchObject({
      artifact: "delivery/selection.json",
      requiredBy: "edl",
      producer: "full_master_ranking",
    });
  });

  it("stays null when the solver halt payload carries no severed dependency", () => {
    const model = buildSolverPanelModel(view({ halt: { halted: false, blockers: [] } }));
    expect(model.severed).toBeNull();
  });
});

describe("reason vocabulary", () => {
  it("describes every documented blocking prefix", () => {
    expect(describeReason("hard_input_missing:a/b.json").kind).toBe("input");
    expect(describeReason("hard_input_uncommitted:a/b.json").detail).toContain("staged");
    expect(describeReason("hard_input_insufficient:a/b.json").kind).toBe("input");
    expect(describeReason("hard_input_below_min_chars:a/b.json").kind).toBe("input");
    expect(describeReason("gate_open:transcript_review").kind).toBe("gate");
    expect(describeReason("door_refused:attempt_cap").detail).toContain("attempt_cap");
    expect(describeReason("tier_not_dispatchable:gate").kind).toBe("tier");
    expect(describeReason("output_write_denied:a/b.json:denied").artifact).toBe("a/b.json");
    expect(describeReason("lease_held_by_gui").kind).toBe("lease");
    expect(describeReason("audio_serialize_inflight:transcribe").kind).toBe("audio");
  });

  it("passes an unknown prefix through instead of inventing copy", () => {
    const copy = describeReason("brand_new_reason:x");
    expect(copy.kind).toBe("other");
    expect(copy.headline).toBe("brand_new_reason:x");
  });

  it("describes deferral codes in operator words", () => {
    expect(describeUnknown("producer_undeclared:a/b.json")).toContain("a/b.json");
    expect(describeUnknown("gate_may_pause:g1_vo_pickup")).toContain("may pause");
    expect(describeUnknown("door_indeterminate")).toContain("dispatch door");
    expect(describeUnknown("something_else")).toBe("something_else");
  });
});
