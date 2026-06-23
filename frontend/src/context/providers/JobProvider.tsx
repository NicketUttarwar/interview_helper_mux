import { createContext, useContext, type ReactNode } from "react";
import type { ExecuteBody } from "../../types";

export interface JobContextValue {
  jobRunning: boolean;
  actionBusy: boolean;
  executeJob: (body: ExecuteBody, opts?: { source?: "user" | "checkpoint_continue" }) => Promise<void>;
  startJobPoll: () => void;
  runNextStage: () => Promise<void>;
  approveWriteAndContinue: (stageId?: string) => Promise<boolean>;
  advanceFromCheckpoint: () => Promise<void>;
}

const JobContext = createContext<JobContextValue | null>(null);

export function JobProvider({
  value,
  children,
}: {
  value: JobContextValue;
  children: ReactNode;
}) {
  return <JobContext.Provider value={value}>{children}</JobContext.Provider>;
}

export function useJob(): JobContextValue {
  const ctx = useContext(JobContext);
  if (!ctx) throw new Error("useJob must be used within JobProvider");
  return ctx;
}
