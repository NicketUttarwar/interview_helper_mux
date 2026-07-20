import { describe, expect, it, vi } from "vitest";
import { navigatePipelineSubTab } from "./navigatePipelineSubTab";
import { makeRunFixture } from "../test/runFixtures";

describe("navigatePipelineSubTab", () => {
  it("navigates when tab is available", () => {
    const onNavigate = vi.fn();
    const run = makeRunFixture({ timeline_ready: true });
    const ok = navigatePipelineSubTab("timeline", run, null, { onNavigate });
    expect(ok).toBe(true);
    expect(onNavigate).toHaveBeenCalledWith("timeline");
  });

  it("blocks legacy tabs in v2", () => {
    const onNavigate = vi.fn();
    const onBlocked = vi.fn();
    const run = makeRunFixture();
    const ok = navigatePipelineSubTab("story", run, null, { onNavigate, onBlocked });
    expect(ok).toBe(false);
    expect(onNavigate).not.toHaveBeenCalled();
    expect(onBlocked).toHaveBeenCalledWith(expect.stringContaining("v2"));
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
