import type { AppConfig } from "../types";

/** Full autopilot UX: in-run finalize + decision wizard (default on). */
export function isFullAutopilotEnabled(config?: AppConfig | null): boolean {
  return config?.journey_ui?.full_autopilot !== false;
}
