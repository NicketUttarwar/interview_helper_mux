import { useApp } from "../../context/AppContext";

/** Surfaces consolidated Flow 1 readiness blockers from journey snapshot. */
export function ProgressionReadinessBanner({ stageId }: { stageId: string }) {
  const { run } = useApp();
  if (stageId !== "topic_coverage_audit") return null;
  const readiness = run?.journey?.flow1_readiness as
    | { ready?: boolean; blockers?: Array<{ layer?: string; message?: string }> }
    | undefined;
  if (!readiness || readiness.ready) return null;
  const blockers = readiness.blockers ?? [];
  if (!blockers.length) return null;
  return (
    <div className="progression-readiness-banner callout warning" data-testid="flow1-readiness-banner">
      <strong>Flow 1 not ready</strong>
      <ul className="progression-readiness-list">
        {blockers.slice(0, 6).map((b, i) => (
          <li key={`${b.layer}-${i}`}>
            {b.layer ? `[${b.layer}] ` : ""}
            {b.message}
          </li>
        ))}
      </ul>
    </div>
  );
}
