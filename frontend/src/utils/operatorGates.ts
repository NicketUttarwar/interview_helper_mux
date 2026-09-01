import type { RunData } from "../types";

export interface OperatorGateView {
  gate_id?: string;
  open?: boolean;
  severity?: string;
  operator_must_act?: boolean;
  stage_status?: string;
  blocks_journey?: boolean;
  blocks_delivery_sidebar?: boolean;
  ui_mode?: string;
  message?: string;
  automation?: {
    owner?: string;
    active?: boolean;
    action?: string;
    state?: string;
  };
}

export function gateView(
  run: RunData | null | undefined,
  gateId: string,
): OperatorGateView | null {
  const raw = run?.operator_gates?.[gateId];
  return raw ?? null;
}

export function gateOperatorMustAct(
  run: RunData | null | undefined,
  gateId: string,
): boolean {
  const view = gateView(run, gateId);
  if (view != null) return Boolean(view.operator_must_act);
  if (gateId === "g1_vo_pickup") {
    return Boolean((run?.g1_missing?.length ?? 0) > 0 && !run?.g1_clear);
  }
  if (gateId === "transcript_review") {
    return Boolean(run?.transcript_review_pending);
  }
  return false;
}

export function g1AutomationPending(run: RunData | null | undefined): boolean {
  const view = gateView(run, "g1_vo_pickup");
  return view?.severity === "automation_pending" || view?.ui_mode === "synthesize_pending";
}

export function g1OptionalOpen(run: RunData | null | undefined): boolean {
  const view = gateView(run, "g1_vo_pickup");
  return view?.severity === "optional" || Boolean(run?.g1_optional);
}
