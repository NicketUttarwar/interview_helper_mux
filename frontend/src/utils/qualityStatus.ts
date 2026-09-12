/** Wire quality-status tokens — keep in sync with interview_mux.quality_status. */

export const WIRE_STATUS_PASS = "pass" as const;
export const WIRE_STATUS_FAIL = "fail" as const;
export const WIRE_STATUS_ADVISORY_FAIL = "advisory_fail" as const;

export type WireQualityStatus =
  | typeof WIRE_STATUS_PASS
  | typeof WIRE_STATUS_FAIL
  | typeof WIRE_STATUS_ADVISORY_FAIL;

export const WIRE_QUALITY_STATUS_VALUES: readonly WireQualityStatus[] = [
  WIRE_STATUS_PASS,
  WIRE_STATUS_FAIL,
  WIRE_STATUS_ADVISORY_FAIL,
] as const;

export function isWireAdvisoryStatus(status: unknown): boolean {
  return String(status || "").trim() === WIRE_STATUS_ADVISORY_FAIL;
}
