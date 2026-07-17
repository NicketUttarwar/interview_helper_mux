import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  isTranscriptReuseEditConsumed,
  markTranscriptReuseEditConsumed,
  shouldOpenTranscriptReuseEdit,
  syncTranscriptReuseEditConsumed,
  transcriptReuseEditPending,
  transcriptReuseEditSettled,
} from "./transcriptReuseEditGate";
import type { RunMeta } from "../types";

const RUN_ID = "exec_test_reuse_gate";

function installSessionStorageMock(): void {
  const store = new Map<string, string>();
  Object.defineProperty(globalThis, "sessionStorage", {
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
      clear: () => {
        store.clear();
      },
    },
    configurable: true,
  });
}

beforeEach(() => {
  installSessionStorageMock();
});

afterEach(() => {
  sessionStorage.removeItem(`mux.transcript_reuse_edit_consumed:${RUN_ID}`);
});

describe("transcriptReuseEditGate", () => {
  it("detects server pending flag", () => {
    expect(transcriptReuseEditPending({ transcript_reuse_pending_edit: true })).toBe(true);
    expect(transcriptReuseEditPending({ transcript_reuse_pending_edit: false })).toBe(false);
  });

  it("treats applied transcribe reuse without pending as settled", () => {
    const meta: RunMeta = {
      stage_reuse: {
        transcribe: {
          action: "accept",
          applied_at: "2026-01-01T00:00:00Z",
        },
      },
    };
    expect(transcriptReuseEditSettled(meta)).toBe(true);
    expect(shouldOpenTranscriptReuseEdit(RUN_ID, meta)).toBe(false);
    expect(isTranscriptReuseEditConsumed(RUN_ID)).toBe(true);
  });

  it("opens only when pending and not consumed", () => {
    const meta: RunMeta = { transcript_reuse_pending_edit: true };
    expect(shouldOpenTranscriptReuseEdit(RUN_ID, meta)).toBe(true);
    markTranscriptReuseEditConsumed(RUN_ID);
    expect(shouldOpenTranscriptReuseEdit(RUN_ID, meta)).toBe(false);
  });

  it("sync marks consumed when reuse settled", () => {
    const meta: RunMeta = {
      stage_reuse: {
        transcribe: {
          action: "accept",
          applied_at: "2026-01-01T00:00:00Z",
        },
      },
    };
    syncTranscriptReuseEditConsumed(RUN_ID, meta);
    expect(isTranscriptReuseEditConsumed(RUN_ID)).toBe(true);
  });
});
