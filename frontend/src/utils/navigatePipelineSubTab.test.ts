import { describe, expect, it, vi } from "vitest";
import { navigatePipelineSubTab } from "./navigatePipelineSubTab";
import { makeRunFixture } from "../test/runFixtures";

describe("navigatePipelineSubTab", () => {
  it("navigates when tab is available", () => {
    const onNavigate = vi.fn();
    const run = makeRunFixture({ story_board_ready: true });
    const ok = navigatePipelineSubTab("story", run, null, { onNavigate });
    expect(ok).toBe(true);
    expect(onNavigate).toHaveBeenCalledWith("story");
  });

  it("blocks locked tabs and reports reason", () => {
    const onNavigate = vi.fn();
    const onBlocked = vi.fn();
    const run = makeRunFixture();
    const ok = navigatePipelineSubTab("story", run, null, { onNavigate, onBlocked });
    expect(ok).toBe(false);
    expect(onNavigate).not.toHaveBeenCalled();
    expect(onBlocked).toHaveBeenCalledWith(expect.stringContaining("content understanding"));
  });

  it("allows force navigation past gating", () => {
    const onNavigate = vi.fn();
    const run = makeRunFixture();
    const ok = navigatePipelineSubTab("story", run, null, {
      onNavigate,
      force: true,
    });
    expect(ok).toBe(true);
    expect(onNavigate).toHaveBeenCalledWith("story");
  });
});
