import { describe, expect, it } from "vitest";
import { isOperatorGateStartResponse } from "./jobStartResponse";

describe("isOperatorGateStartResponse", () => {
  it("treats stage reuse pause as operator gate", () => {
    expect(
      isOperatorGateStartResponse({
        ok: false,
        error:
          "Stage 'speaker_roles' can reuse outputs from a previous execution (exec_1). Choose reuse or run fresh in the GUI, then continue.",
        needs_stage_reuse: true,
        stage: "speaker_roles",
      }),
    ).toBe(true);
  });

  it("treats write approval pause as operator gate", () => {
    expect(
      isOperatorGateStartResponse({
        ok: false,
        error: "Review staged outputs before continuing.",
        awaiting_write_approval: true,
        pending_write_stage: "ingest",
      }),
    ).toBe(true);
  });

  it("treats handoff pause as operator gate", () => {
    expect(
      isOperatorGateStartResponse({
        ok: false,
        error: "Review AI outputs before continuing.",
        needs_handoff_review: true,
      }),
    ).toBe(true);
  });

  it("treats generic needs_operator pause as operator gate", () => {
    expect(
      isOperatorGateStartResponse({
        ok: false,
        error: "Enable OpenAI in API consents before running this stage.",
        needs_operator: true,
      }),
    ).toBe(true);
  });

  it("does not treat real failures as operator gate", () => {
    expect(
      isOperatorGateStartResponse({
        ok: false,
        error: "Could not start pipeline — directory lock busy.",
      }),
    ).toBe(false);
  });

  it("returns false when job started successfully", () => {
    expect(isOperatorGateStartResponse({ ok: true })).toBe(false);
  });
});
