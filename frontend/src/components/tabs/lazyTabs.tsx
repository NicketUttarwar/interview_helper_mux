import { lazy } from "react";

export const LazyStartTab = lazy(() =>
  import("./StartTab").then((m) => ({ default: m.StartTab })),
);

export const LazyExecutionsTab = lazy(() =>
  import("./ExecutionsTab").then((m) => ({ default: m.ExecutionsTab })),
);

export const LazyPipelineTab = lazy(() =>
  import("./PipelineTab").then((m) => ({ default: m.PipelineTab })),
);

export const LazyLogsTab = lazy(() =>
  import("./LogsTab").then((m) => ({ default: m.LogsTab })),
);

const tabImporters = {
  start: () => import("./StartTab"),
  executions: () => import("./ExecutionsTab"),
  pipeline: () => import("./PipelineTab"),
  logs: () => import("./LogsTab"),
} as const;

export type LazyTabId = keyof typeof tabImporters;

export function prefetchTab(tab: LazyTabId): void {
  void tabImporters[tab]();
}
