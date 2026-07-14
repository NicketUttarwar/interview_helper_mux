import { describe, expect, it } from "vitest";
import { validateArtifactWrite } from "./validateArtifact";

const validRunMeta = {
  execution_id: "exec_001_abcdef012345",
  execution_number: 1,
  input_audio_path: "/ASSETS/input/sample.wav",
  source_audio_hash: "a".repeat(64),
  source_audio_hash_short: "a".repeat(12),
  created_at: "2026-07-14T12:00:00Z",
  updated_at: "2026-07-14T12:00:00Z",
  operator_phase: "prepare" as const,
};

describe("validateArtifactWrite", () => {
  it("returns ok for unknown artifact paths without loading schemas", async () => {
    const result = await validateArtifactWrite("not/a/real/artifact.json", { any: "data" });
    expect(result).toEqual({ ok: true });
  });

  it("rejects invalid data for a known artifact path", async () => {
    const result = await validateArtifactWrite("run_meta.json", {
      execution_number: "not-a-number",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.length).toBeGreaterThan(0);
    }
  });

  it("accepts valid data and reuses cached schema on repeat calls", async () => {
    const first = await validateArtifactWrite("run_meta.json", validRunMeta);
    const second = await validateArtifactWrite("run_meta.json", validRunMeta);
    expect(first).toEqual({ ok: true });
    expect(second).toEqual({ ok: true });
  });
});
