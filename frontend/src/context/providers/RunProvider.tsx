import { createContext, useContext, type ReactNode } from "react";
import type { OpenRunOptions, RunData, RunSummary, StageInfo } from "../../types";

export interface RunContextValue {
  runId: string | null;
  run: RunData | null;
  runs: RunSummary[];
  selectedStageId: string | null;
  selectedStage: StageInfo | undefined;
  openRunLoading: boolean;
  openRun: (runId: string, opts?: OpenRunOptions) => Promise<void>;
  refreshRun: () => Promise<RunData | null>;
  selectStage: (stageId: string) => Promise<void>;
  startRun: (inputPath: string, flowIntent?: string) => Promise<void>;
  refreshHome: (opts?: { enrichRuns?: boolean }) => Promise<void>;
}

const RunContext = createContext<RunContextValue | null>(null);

export function RunProvider({
  value,
  children,
}: {
  value: RunContextValue;
  children: ReactNode;
}) {
  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun(): RunContextValue {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useRun must be used within RunProvider");
  return ctx;
}
