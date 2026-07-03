import { afterEach, describe, expect, it } from "vitest";
import {
  autoNavTargetKey,
  clearAutoNavLedgerForTests,
  isAutoNavConsumed,
  markAutoNavConsumed,
  resetAutoNavLedgerIfServerChanged,
  stageHadAutoNavigation,
} from "./autoNavigationLedger";

describe("autoNavigationLedger", () => {
  afterEach(() => {
    clearAutoNavLedgerForTests();
  });

  it("keys stage and step together", () => {
    expect(autoNavTargetKey({ stageId: "disfluency_review", stepId: "review_fillers" })).toBe(
      "disfluency_review::review_fillers",
    );
  });

  it("tracks consumed targets per server session", () => {
    resetAutoNavLedgerIfServerChanged("server-a");
    const target = { stageId: "disfluency_review", stepId: "review_fillers" };
    expect(isAutoNavConsumed(target)).toBe(false);
    markAutoNavConsumed(target);
    expect(isAutoNavConsumed(target)).toBe(true);
    expect(stageHadAutoNavigation("disfluency_review")).toBe(true);
    expect(stageHadAutoNavigation("transcript_review")).toBe(false);
  });

  it("resets when the GUI server restarts", () => {
    resetAutoNavLedgerIfServerChanged("server-a");
    markAutoNavConsumed({ stageId: "disfluency_review", stepId: "review_fillers" });
    resetAutoNavLedgerIfServerChanged("server-b");
    expect(
      isAutoNavConsumed({ stageId: "disfluency_review", stepId: "review_fillers" }),
    ).toBe(false);
  });

  it("restores ledger from sessionStorage for the same server session", () => {
    if (typeof sessionStorage === "undefined") return;
    resetAutoNavLedgerIfServerChanged("server-a");
    markAutoNavConsumed({ stageId: "disfluency_review", stepId: "review_fillers" });
    clearAutoNavLedgerForTests();
    resetAutoNavLedgerIfServerChanged("server-a");
    expect(
      isAutoNavConsumed({ stageId: "disfluency_review", stepId: "review_fillers" }),
    ).toBe(true);
  });
});
