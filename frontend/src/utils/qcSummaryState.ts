/** G-02 / GUI-QC-01 — QC card display states + honest blocksShip. */

import {
  WIRE_STATUS_ADVISORY_FAIL,
  WIRE_STATUS_PASS,
  isWireAdvisoryStatus,
} from "./qualityStatus";

/** Display states: wire `fail` maps to blocking_fail; advisory_fail stays wire token. */
export type QcDisplayState =
  | typeof WIRE_STATUS_PASS
  | typeof WIRE_STATUS_ADVISORY_FAIL
  | "blocking_fail"
  | "waived";

export interface QcSummaryLike {
  passed?: boolean;
  blocking?: boolean;
  advisory?: boolean;
  status?: string;
  publish_allowed?: boolean;
  waived?: boolean;
  [key: string]: unknown;
}

export function resolveQcDisplayState(summary: QcSummaryLike | null | undefined): QcDisplayState {
  if (!summary) return WIRE_STATUS_ADVISORY_FAIL;
  const status = String(summary.status || "").toLowerCase();
  if (
    summary.waived === true ||
    status === "waived" ||
    status === "waived_unattended" ||
    status === "quality_waived"
  ) {
    return "waived";
  }
  if (summary.passed) return WIRE_STATUS_PASS;
  if (isWireAdvisoryStatus(status) || summary.advisory === true) {
    return WIRE_STATUS_ADVISORY_FAIL;
  }
  if (summary.blocking === true || summary.advisory === false) return "blocking_fail";
  return WIRE_STATUS_ADVISORY_FAIL;
}

/**
 * blocksShip iff publish_allowed is false (or finalize refuse), not only summary.blocking.
 * Aligns with A-04: waived_unattended alone must not look ship-green.
 */
export function resolveQcBlocksShip(
  summary: QcSummaryLike | null | undefined,
  qcKey: string,
  allSummaries?: Record<string, QcSummaryLike> | null,
): boolean {
  if (!summary) return false;
  if (typeof summary.publish_allowed === "boolean") {
    return summary.publish_allowed === false;
  }
  const pmq = allSummaries?.post_master_quality;
  if (
    (qcKey === "listen_delight" || qcKey === "post_master_quality") &&
    pmq &&
    typeof pmq.publish_allowed === "boolean"
  ) {
    return pmq.publish_allowed === false;
  }
  // Finalize refuse / explicit blocking fail without publish_allowed field.
  if (summary.blocking === true && summary.advisory === false) return true;
  if (summary.blocking === true && qcKey === "post_master_quality") return true;
  return false;
}
