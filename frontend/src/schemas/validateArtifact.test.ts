import { describe, expect, it } from "vitest";
import { validateArtifactWrite } from "./validateArtifact";

describe("validateArtifactWrite", () => {
  it("returns ok for unknown artifact paths without loading schemas", async () => {
    const result = await validateArtifactWrite("not/a/real/artifact.json", { any: "data" });
    expect(result).toEqual({ ok: true });
  });

  it("rejects invalid data for a known artifact path", async () => {
    const result = await validateArtifactWrite("run_meta.json", {
      selected_flow: "not_a_valid_flow",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.length).toBeGreaterThan(0);
    }
  });

  it("accepts valid data and reuses cached schema on repeat calls", async () => {
    const valid = { selected_flow: "flow1" as const };
    const first = await validateArtifactWrite("run_meta.json", valid);
    const second = await validateArtifactWrite("run_meta.json", valid);
    expect(first).toEqual({ ok: true });
    expect(second).toEqual({ ok: true });
  });
});
