import { describe, expect, it, vi, beforeEach } from "vitest";

const apiMock = vi.fn();
vi.mock("../api/client", () => ({
  api: (...args: unknown[]) => apiMock(...args),
}));

import { completeAnalysisProfile } from "./analysisProfileCheckpoint";

describe("completeAnalysisProfile", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockResolvedValue({});
  });

  it("PUTs profile data before verify POST", async () => {
    const order: string[] = [];
    apiMock.mockImplementation(async (url: string, init?: { method?: string }) => {
      order.push(`${init?.method ?? "GET"}:${url}`);
      return {};
    });

    await completeAnalysisProfile({
      runId: "exec_001",
      data: { meta: {} } as never,
      verify: true,
      refreshRun: async () => null,
      advanceFromCheckpoint: async () => {},
      showToast: () => {},
    });

    const putIdx = order.findIndex((s) => s.startsWith("PUT:"));
    const verifyIdx = order.findIndex((s) => s.includes("/verify"));
    expect(putIdx).toBeGreaterThanOrEqual(0);
    expect(verifyIdx).toBeGreaterThan(putIdx);
  });

  it("verify-only skips PUT", async () => {
    const order: string[] = [];
    apiMock.mockImplementation(async (url: string, init?: { method?: string }) => {
      order.push(`${init?.method ?? "GET"}:${url}`);
      return {};
    });

    await completeAnalysisProfile({
      runId: "exec_001",
      verify: true,
      refreshRun: async () => null,
      advanceFromCheckpoint: async () => {},
      showToast: () => {},
    });

    expect(order.some((s) => s.startsWith("PUT:"))).toBe(false);
    expect(order.some((s) => s.includes("/verify"))).toBe(true);
  });
});
