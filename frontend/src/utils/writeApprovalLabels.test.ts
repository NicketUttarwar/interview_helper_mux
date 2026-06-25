import { describe, expect, it } from "vitest";
import { writeApprovalPrimaryLabel, writeApprovalSaveInProgressLabel } from "./writeApprovalLabels";

describe("writeApprovalPrimaryLabel", () => {
  it("uses a single save-all label with optional file count", () => {
    expect(writeApprovalPrimaryLabel()).toBe("Save all files & continue");
    expect(writeApprovalPrimaryLabel(3)).toBe("Save all 3 files & continue");
    expect(writeApprovalPrimaryLabel(1)).toBe("Save all files & continue");
  });
});

describe("writeApprovalSaveInProgressLabel", () => {
  it("describes background save with optional file count", () => {
    expect(writeApprovalSaveInProgressLabel()).toContain("please wait");
    expect(writeApprovalSaveInProgressLabel(3)).toContain("3 files");
  });
});
