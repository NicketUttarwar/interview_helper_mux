import { createContext, useContext, type ReactNode } from "react";
import type { AppTab, LogStreamTab, PipelineSubTab } from "../../types";

export interface SessionContextValue {
  sessionReady: boolean;
  sessionLoadError: string | null;
  serverActiveRunId: string | null;
  activeTab: AppTab;
  pipelineSubTab: PipelineSubTab;
  setActiveTab: (tab: AppTab) => void;
  setPipelineSubTab: (tab: PipelineSubTab) => void;
  clearSession: () => Promise<void>;
  activityLogTab: LogStreamTab;
  activityLogCollapsed: boolean;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({
  value,
  children,
}: {
  value: SessionContextValue;
  children: ReactNode;
}) {
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
