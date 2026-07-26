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
    expect(autoNavTargetKey({ stageId: "transcript_review", stepId: "review_transcript" })).toBe(
      "transcript_review::review_transcript",
    );
  });

  it("tracks consumed targets per server session", () => {
    resetAutoNavLedgerIfServerChanged("server-a");
    const target = { stageId: "transcript_review", stepId: "review_transcript" };
    expect(isAutoNavConsumed(target)).toBe(false);
    markAutoNavConsumed(target);
    expect(isAutoNavConsumed(target)).toBe(true);
    expect(stageHadAutoNavigation("transcript_review")).toBe(true);
    expect(stageHadAutoNavigation("ingest")).toBe(false);
  });

  it("resets when the GUI server restarts", () => {
    resetAutoNavLedgerIfServerChanged("server-a");
    markAutoNavConsumed({ stageId: "transcript_review", stepId: "review_transcript" });
    resetAutoNavLedgerIfServerChanged("server-b");
    expect(
      isAutoNavConsumed({ stageId: "transcript_review", stepId: "review_transcript" }),
    ).toBe(false);
  });

  it("restores ledger from sessionStorage for the same server session", () => {
    if (typeof sessionStorage === "undefined") return;
    resetAutoNavLedgerIfServerChanged("server-a");
    markAutoNavConsumed({ stageId: "transcript_review", stepId: "review_transcript" });
    clearAutoNavLedgerForTests();
    resetAutoNavLedgerIfServerChanged("server-a");
    expect(
      isAutoNavConsumed({ stageId: "transcript_review", stepId: "review_transcript" }),
    ).toBe(true);
  });

  it("treats any step on a stage as consumed for stageHadAutoNavigation", () => {
    resetAutoNavLedgerIfServerChanged("server-a");
    markAutoNavConsumed({ stageId: "transcript_review", stepId: "review_transcript" });
    expect(stageHadAutoNavigation("transcript_review")).toBe(true);
    // A different step on the same source stage still counts as guided.
    expect(isAutoNavConsumed({ stageId: "transcript_review", stepId: "complete_review" })).toBe(
      false,
    );
  });
});
