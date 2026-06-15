import type { SfxBlockReason } from "../../types";
import { sfxBlockKindLabel } from "../../utils/sfxBlockReasons";

export function SfxBlockedPanel({
  onOpen,
  reasons,
}: {
  onOpen: () => void;
  reasons?: SfxBlockReason[];
}) {
  const grouped = (reasons || []).reduce<Record<string, SfxBlockReason[]>>((acc, reason) => {
    const list = acc[reason.kind] || [];
    list.push(reason);
    acc[reason.kind] = list;
    return acc;
  }, {});

  const kinds: SfxBlockReason["kind"][] = ["g1_5", "qa_fail", "spend", "venv"];

  return (
    <div className="quality-offer-card sfx-blocked-card">
      <p className="hint">
        <strong>SFX generation blocked:</strong> resolve the issues below before running MMAudio.
      </p>
      {kinds.some((kind) => grouped[kind]?.length) ? (
        <div className="sfx-block-reasons">
          {kinds.map((kind) => {
            const rows = grouped[kind];
            if (!rows?.length) return null;
            return (
              <div key={kind} className="sfx-block-reason-group">
                <h4>{sfxBlockKindLabel(kind)}</h4>
                <ul className="muted sm">
                  {rows.map((reason, idx) => (
                    <li key={idx}>
                      {reason.message}
                      {reason.asset_ids?.length
                        ? ` (${reason.asset_ids.slice(0, 6).join(", ")}${reason.asset_ids.length > 6 ? "…" : ""})`
                        : null}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="muted">
          Open <strong>Sfx prompt craft</strong> to edit prompts, tune influence, and approve.
        </p>
      )}
      <div className="flow-choice">
        <button type="button" className="btn primary sm" onClick={onOpen}>
          Open prompt craft
        </button>
      </div>
    </div>
  );
}
