/**
 * Read model for `GET /api/runs/{run_id}/solver-decision` — plan §10.2.
 *
 * The solver is shadow-only (`MUX_SOLVER_AUTHORITATIVE` / `MUX_SOLVER_SHADOW` both
 * default off), so `operator/solver_decision.jsonl` is normally absent. Two rules
 * follow, and both are load-bearing for the panel:
 *
 * 1. Absent or contentless telemetry is `no_data` — never "nothing is runnable".
 * 2. `deferred` is not blocked. The solver defers when a contract declares no hard
 *    inputs, i.e. it has no opinion and the walk decides. Rendering a deferral as a
 *    blocker would send an operator hunting for a producer that was never missing.
 * 3. An empty admissible set has two causes that need opposite operator responses, so
 *    `halt_kind` is read before saying "nothing is runnable": a GUI lease empties the
 *    set while another session walks the run (`lease_pause`, clears itself), where a
 *    `structural_halt` needs someone to go unblock a producer.
 */

export interface SolverVerdictRow {
  stage: string;
  admissible?: boolean;
  tier?: string;
  phase?: string;
  seed_index?: number;
  confident?: boolean;
  reason?: string;
  reasons?: string[];
  unknowns?: string[];
  detail?: { producers?: Record<string, string> } & Record<string, unknown>;
}

export interface SolverDecisionRow {
  at?: string;
  posture?: string;
  lease_ok?: boolean;
  admissible?: string[];
  would_choose?: string | null;
  would_choose_confident?: string | null;
  deferred?: string[];
  seed_first_incomplete?: string | null;
  halted?: boolean;
  /** `""` | `"lease_pause"` | `"structural_halt"`. Absent on rows written before 84b79344. */
  halt_kind?: string;
  /** Mirrors `halt_kind === "lease_pause"`; absent on the same legacy rows. */
  paused?: boolean;
  excluded?: SolverVerdictRow[];
  admissible_detail?: SolverVerdictRow[];
}

/** `""` | `"lease_pause"` | `"structural_halt"` — `Decision.halt_kind` in `solver.py`. */
export type SolverHaltKind = "" | "lease_pause" | "structural_halt";

export const LEASE_PAUSE = "lease_pause";
export const STRUCTURAL_HALT = "structural_halt";
/** The reason code a lease pause carries (`solver.py` `LEASE_REASON`). */
export const LEASE_REASON_CODE = "lease_held_by_gui";

export interface SolverHaltBlocker {
  stage?: string;
  phase?: string;
  reason?: string;
  reasons?: string[];
  producers?: Record<string, string>;
  confident?: boolean;
}

/** One proven-severed dependency from `ship_reachability.halt_payload`. */
export interface SolverHaltUnmet {
  artifact?: string;
  required_by?: string;
  producers?: string[];
  blocker?: string;
  defect_id?: string;
  resume?: string;
}

export interface SolverHaltPayload {
  halted?: boolean;
  /** `halt_payload` names the halt kind `kind`, not `halt_kind` as the row does. */
  kind?: string;
  paused?: boolean;
  /** `lease_held_by_gui` while paused, `""` otherwise. */
  reason_code?: string;
  posture?: string;
  lease_ok?: boolean;
  seed_first_incomplete?: string | null;
  blockers?: SolverHaltBlocker[];
  unmet?: SolverHaltUnmet[];
  resume?: string;
  reason?: string;
  halt_enabled?: boolean;
}

export interface SolverDecisionView {
  artifact?: string;
  authoritative?: boolean;
  shadow_logging?: boolean;
  writable?: boolean;
  ownership_row_registered?: boolean;
  rows?: SolverDecisionRow[];
  live?: SolverDecisionRow | null;
  halt?: SolverHaltPayload | null;
}

export type BlockedKind =
  | "input"
  | "gate"
  | "door"
  | "lease"
  | "tier"
  | "ownership"
  | "audio"
  | "other";

export interface BlockedStage {
  stage: string;
  phase: string;
  /** Raw solver reason, e.g. `hard_input_missing:understanding/speakers.json`. */
  reason: string;
  kind: BlockedKind;
  headline: string;
  detail: string;
  /** Artifact path the reason names, when it names one. */
  artifact: string | null;
  /** Stage that would satisfy the unmet input, from the contract's declared producer. */
  producer: string | null;
  /** Further reasons beyond the most specific one. */
  alsoBlockedBy: string[];
  confident: boolean;
}

/** Blocked stages sharing one reason — one gate can exclude sixty stages. */
export interface BlockedGroup {
  reason: string;
  kind: BlockedKind;
  headline: string;
  detail: string;
  artifact: string | null;
  producer: string | null;
  stages: string[];
}

export interface DeferredStage {
  stage: string;
  phase: string;
  /** Why the solver has no opinion, in operator words. */
  why: string;
  codes: string[];
}

export interface SeveredHalt {
  reason: string;
  resume: string;
  unmet: {
    artifact: string;
    requiredBy: string;
    producer: string;
    resume: string;
    blocker: string;
  }[];
}

export type SolverPanelState = "no_data" | "paused" | "halted" | "moving" | "complete";

export interface SolverPanelModel {
  state: SolverPanelState;
  /** Which row the model describes; `null` when there is nothing to describe. */
  source: "live" | "logged" | null;
  at: string;
  posture: string;
  leaseOk: boolean;
  /** Why the admissible set is empty, resolved with the legacy fallback below. */
  haltKind: SolverHaltKind;
  paused: boolean;
  /** `lease_held_by_gui` while paused, `""` otherwise. */
  haltReasonCode: string;
  /** Stages held only by the lease — waiting for another session, not blocked. */
  waiting: string[];
  shadowOnly: boolean;
  shadowLogging: boolean;
  loggedRowCount: number;
  artifact: string;
  wouldChoose: string | null;
  wouldChooseConfident: string | null;
  seedFirstIncomplete: string | null;
  runnable: string[];
  confidentRunnable: string[];
  blocked: BlockedStage[];
  blockedGroups: BlockedGroup[];
  deferred: DeferredStage[];
  doneStages: string[];
  severed: SeveredHalt | null;
}

/** Exclusions that are not blockers: a finished stage is not a reason nothing runs. */
const NON_BLOCKING_REASONS = new Set(["already_done", "not_a_pipeline_stage"]);

const EMPTY_MODEL: SolverPanelModel = {
  state: "no_data",
  source: null,
  at: "",
  posture: "",
  leaseOk: true,
  haltKind: "",
  paused: false,
  haltReasonCode: "",
  waiting: [],
  shadowOnly: true,
  shadowLogging: false,
  loggedRowCount: 0,
  artifact: "operator/solver_decision.jsonl",
  wouldChoose: null,
  wouldChooseConfident: null,
  seedFirstIncomplete: null,
  runnable: [],
  confidentRunnable: [],
  blocked: [],
  blockedGroups: [],
  deferred: [],
  doneStages: [],
  severed: null,
};

function splitReason(reason: string): { prefix: string; arg: string } {
  const idx = reason.indexOf(":");
  if (idx < 0) return { prefix: reason, arg: "" };
  return { prefix: reason.slice(0, idx), arg: reason.slice(idx + 1) };
}

interface ReasonCopy {
  kind: BlockedKind;
  headline: string;
  detail: string;
  artifact: string | null;
}

/** Turn a prefixed solver reason into operator copy. Unknown prefixes pass through. */
export function describeReason(reason: string): ReasonCopy {
  const { prefix, arg } = splitReason(reason);
  switch (prefix) {
    case "hard_input_missing":
      return {
        kind: "input",
        headline: "Required input has not been produced",
        detail: `${arg} does not exist yet.`,
        artifact: arg,
      };
    case "hard_input_uncommitted":
      return {
        kind: "input",
        headline: "Required input is staged but not committed",
        detail: `${arg} exists as a staged write; the solver only counts committed artifacts.`,
        artifact: arg,
      };
    case "hard_input_insufficient":
      return {
        kind: "input",
        headline: "Required input is incomplete",
        detail: `${arg} exists but its completeness check did not pass.`,
        artifact: arg,
      };
    case "hard_input_below_min_chars":
      return {
        kind: "input",
        headline: "Required input is smaller than its contract minimum",
        detail: `${arg} is below the minimum size its consumer declares.`,
        artifact: arg,
      };
    case "gate_open":
      return {
        kind: "gate",
        headline: "An operator gate is open",
        detail: `Gate ${arg} is waiting on a decision in this posture.`,
        artifact: null,
      };
    case "door_refused":
      return {
        kind: "door",
        headline: "The dispatch door refused this stage",
        detail: arg ? `Door reason: ${arg}.` : "The door refused without a reason.",
        artifact: null,
      };
    case "tier_not_dispatchable":
      return {
        kind: "tier",
        headline: "Stage tier is not dispatchable",
        detail: `Tier ${arg || "unknown"} is not a pipeline tier, so the walk never dispatches it.`,
        artifact: null,
      };
    case "output_write_denied": {
      const [path, ...rest] = arg.split(":");
      return {
        kind: "ownership",
        headline: "A declared output is not writable",
        detail: `${path} is denied by the ownership matrix${rest.length ? ` (${rest.join(":")})` : ""}.`,
        artifact: path || null,
      };
    }
    case "lease_held_by_gui":
      return {
        kind: "lease",
        headline: "The GUI holds the run lease",
        detail: "An operator session is walking the run, so the solver would not act.",
        artifact: null,
      };
    case "audio_serialize_inflight":
      return {
        kind: "audio",
        headline: "Another audio job is in flight",
        detail: `${arg} is mutating audio; audio stages run one at a time.`,
        artifact: null,
      };
    default:
      return {
        kind: "other",
        headline: reason || "Excluded without a reason",
        detail: "",
        artifact: null,
      };
  }
}

/** Why the solver has no opinion about a stage, in operator words. */
export function describeUnknown(code: string): string {
  const { prefix, arg } = splitReason(code);
  switch (prefix) {
    case "hard_inputs_undeclared":
      return "its contract declares no hard inputs, so the solver has no prerequisites to check";
    case "contract_absent":
      return "no stage contract was found";
    case "outputs_undeclared":
      return "its contract declares no outputs";
    case "producer_undeclared":
      return `no producer is declared for ${arg}`;
    case "when_indeterminate":
      return `the conditional guard on ${arg} could not be evaluated`;
    case "input_is_path_spec":
      return `${arg} is a path pattern, not a single artifact`;
    case "gate_indeterminate":
      return `gate ${arg} could not be read`;
    case "gate_may_pause":
      return `gate ${arg} may pause in this posture but is not guaranteed to`;
    case "gate_auto_accept_pending":
      return `gate ${arg} auto-accepts in this posture`;
    case "gate_optional_by_config":
      return `gate ${arg} is optional by configuration`;
    case "ownership_indeterminate":
      return `ownership of ${arg} could not be resolved`;
    case "door_indeterminate":
      return "the dispatch door could not be evaluated";
    default:
      return code;
  }
}

function producerFor(
  verdict: SolverVerdictRow,
  artifact: string | null,
  fallback: Map<string, Record<string, string>>,
): string | null {
  if (!artifact) return null;
  const declared = verdict.detail?.producers?.[artifact];
  if (declared) return declared;
  return fallback.get(verdict.stage)?.[artifact] ?? null;
}

/**
 * Why the admissible set is empty, for one row.
 *
 * Rows written before `halt_kind` existed carry no answer, and the two failure
 * directions are not symmetric: calling a real halt a pause hides a stuck pipeline
 * behind "this clears on its own", where calling a pause a halt only over-alarms. So
 * an absent or unrecognised `halt_kind` resolves to `structural_halt` — today's
 * behaviour — and only the literal `lease_pause` stamp earns the calmer reading.
 * `lease_ok` is deliberately not consulted as a substitute; on a legacy row it is not
 * evidence the backend meant a pause.
 */
export function resolveHaltKind(row: SolverDecisionRow | null | undefined): SolverHaltKind {
  if (!row) return "";
  const nothingRunnable = row.halted === true || (row.admissible?.length ?? 0) === 0;
  if (!nothingRunnable) return "";
  return row.halt_kind === LEASE_PAUSE ? LEASE_PAUSE : STRUCTURAL_HALT;
}

function hasContent(row: SolverDecisionRow | null | undefined): boolean {
  if (!row) return false;
  // A lease pause persists a decision with no verdicts at all (`_log_authoritative_pause`),
  // so the stamp is the whole content. It is positive information, not absent telemetry.
  if (row.halt_kind === LEASE_PAUSE) return true;
  return Boolean(
    row.excluded?.length ||
      row.admissible?.length ||
      row.deferred?.length ||
      row.admissible_detail?.length,
  );
}

function severedFrom(halt: SolverHaltPayload | null | undefined): SeveredHalt | null {
  if (!halt) return null;
  const unmet = halt.unmet ?? [];
  if (!unmet.length && !halt.resume) return null;
  return {
    reason: halt.reason ?? "ship path proven unreachable",
    resume: halt.resume ?? unmet[0]?.resume ?? "",
    unmet: unmet.map((u) => ({
      artifact: u.artifact ?? "",
      requiredBy: u.required_by ?? "",
      producer: (u.producers ?? [])[0] ?? "",
      resume: u.resume ?? "",
      blocker: u.blocker ?? "",
    })),
  };
}

/**
 * Collapse the decision view into what the panel renders.
 *
 * Prefers the live evaluation the endpoint computes; falls back to the newest logged
 * row (`rows` is oldest-first) and, when neither says anything, to `no_data`.
 */
export function buildSolverPanelModel(
  view: SolverDecisionView | null | undefined,
): SolverPanelModel {
  if (!view) return EMPTY_MODEL;

  const logged = view.rows ?? [];
  const base: SolverPanelModel = {
    ...EMPTY_MODEL,
    shadowOnly: view.authoritative !== true,
    shadowLogging: view.shadow_logging === true,
    loggedRowCount: logged.length,
    artifact: view.artifact || EMPTY_MODEL.artifact,
    severed: severedFrom(view.halt),
  };

  let row: SolverDecisionRow | null = null;
  let source: "live" | "logged" | null = null;
  if (hasContent(view.live)) {
    row = view.live ?? null;
    source = "live";
  } else {
    for (let i = logged.length - 1; i >= 0; i -= 1) {
      if (hasContent(logged[i])) {
        row = logged[i];
        source = "logged";
        break;
      }
    }
  }
  if (!row || !source) return base;

  const haltProducers = new Map<string, Record<string, string>>();
  for (const blocker of view.halt?.blockers ?? []) {
    if (blocker.stage && blocker.producers) {
      haltProducers.set(blocker.stage, blocker.producers);
    }
  }

  const haltKind = resolveHaltKind(row);
  const paused = haltKind === LEASE_PAUSE;

  const blocked: BlockedStage[] = [];
  const doneStages: string[] = [];
  const waiting: string[] = [];
  for (const verdict of row.excluded ?? []) {
    const reasons = verdict.reasons ?? (verdict.reason ? [verdict.reason] : []);
    const primary = reasons[0] ?? "";
    if (!primary || NON_BLOCKING_REASONS.has(primary)) {
      if (primary === "already_done") doneStages.push(verdict.stage);
      continue;
    }
    // The lease excludes every stage at once, so during a pause it is the run-level
    // wait condition rather than sixty blockers to chase. Outside a pause it stays a
    // blocker, which is what legacy rows without `halt_kind` keep rendering as.
    if (paused && primary === LEASE_REASON_CODE) {
      waiting.push(verdict.stage);
      continue;
    }
    const copy = describeReason(primary);
    blocked.push({
      stage: verdict.stage,
      phase: verdict.phase ?? "",
      reason: primary,
      kind: copy.kind,
      headline: copy.headline,
      detail: copy.detail,
      artifact: copy.artifact,
      producer: producerFor(verdict, copy.artifact, haltProducers),
      alsoBlockedBy: reasons.slice(1),
      confident: verdict.confident !== false,
    });
  }

  const groups = new Map<string, BlockedGroup>();
  for (const item of blocked) {
    const existing = groups.get(item.reason);
    if (existing) {
      existing.stages.push(item.stage);
      existing.producer = existing.producer ?? item.producer;
      continue;
    }
    groups.set(item.reason, {
      reason: item.reason,
      kind: item.kind,
      headline: item.headline,
      detail: item.detail,
      artifact: item.artifact,
      producer: item.producer,
      stages: [item.stage],
    });
  }

  const detailByStage = new Map<string, SolverVerdictRow>();
  for (const verdict of row.admissible_detail ?? []) {
    detailByStage.set(verdict.stage, verdict);
  }
  const deferred: DeferredStage[] = (row.deferred ?? []).map((stage) => {
    const verdict = detailByStage.get(stage);
    const codes = verdict?.unknowns ?? [];
    return {
      stage,
      phase: verdict?.phase ?? "",
      why: codes.length
        ? codes.map(describeUnknown).join("; ")
        : "the solver could not prove a verdict from contracts",
      codes: [...codes],
    };
  });

  const runnable = row.admissible ?? [];
  const deferredSet = new Set(deferred.map((d) => d.stage));

  let state: SolverPanelState = "moving";
  if (paused) {
    // Empty because someone else holds the run. Nothing here is stuck.
    state = "paused";
  } else if (runnable.length === 0 || row.halted === true) {
    // Every stage done is a finished run, not a halt with a cause to chase.
    state = blocked.length === 0 && doneStages.length > 0 ? "complete" : "halted";
  }

  return {
    ...base,
    state,
    source,
    at: row.at ?? "",
    posture: row.posture ?? "",
    leaseOk: row.lease_ok !== false,
    haltKind,
    paused,
    haltReasonCode: paused ? LEASE_REASON_CODE : "",
    waiting,
    wouldChoose: row.would_choose ?? null,
    wouldChooseConfident: row.would_choose_confident ?? null,
    seedFirstIncomplete: row.seed_first_incomplete ?? null,
    runnable: [...runnable],
    confidentRunnable: runnable.filter((s) => !deferredSet.has(s)),
    blocked,
    blockedGroups: [...groups.values()].sort((a, b) => b.stages.length - a.stages.length),
    deferred,
    doneStages,
  };
}
