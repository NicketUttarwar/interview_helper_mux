import { useApp } from "../../context/AppContext";

/** Surfaces consolidated delivery readiness blockers from journey snapshot. */
export function ProgressionReadinessBanner({ stageId }: { stageId: string }) {
  const { run } = useApp();
  if (stageId !== "topic_coverage_audit") return null;
  const readiness = run?.journey?.delivery_readiness;
  if (!readiness || readiness.ready) return null;
  const blockers = readiness.blockers ?? [];
  if (!blockers.length) return null;
  return (
    <div className="progression-readiness-banner callout warning" data-testid="delivery-readiness-banner">
      <strong>Delivery not ready</strong>
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
