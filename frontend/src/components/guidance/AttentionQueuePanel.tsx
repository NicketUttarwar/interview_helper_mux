import { useState } from "react";
import { useApp } from "../../context/AppContext";
import {
  listAttentionItems,
  listRequiredAttentionItems,
  type AttentionItem,
} from "../../utils/attentionQueue";
import { attentionItemToSubstep } from "../../utils/stageSubsteps";
import { SubstepRow } from "../pipeline/SubstepRow";

const COLLAPSE_KEY = "attention_queue_collapsed";

interface Props {
  compact?: boolean;
  /** Hide when the only required item is write approval (inline panel covers it). */
  hideWhenSingleWriteApproval?: boolean;
}

export function AttentionQueuePanel({ compact, hideWhenSingleWriteApproval }: Props) {
  const {
    run,
    apiGrants,
    setActiveTab,
    setPipelineSubTab,
    activateSubstep,
  } = useApp();

  const [collapsed, setCollapsed] = useState(() => {
    try {
      return sessionStorage.getItem(COLLAPSE_KEY) === "1";
    } catch {
      return false;
    }
  });

  if (!run) return null;

  const required = listRequiredAttentionItems(run, apiGrants);
  const optional = listAttentionItems(run, apiGrants).filter((i) => i.optional);

  if (
    hideWhenSingleWriteApproval &&
    required.length === 1 &&
    required[0].kind === "write_approval"
  ) {
    return null;
  }

  if (required.length === 0 && optional.length === 0) return null;

  const toggleCollapse = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      sessionStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
    } catch {
      /* ignore */
    }
  };

  const goToItem = (item: AttentionItem) => {
    activateSubstep(attentionItemToSubstep(item));
  };

  if (compact) {
    if (required.length <= 1) return null;
    return (
      <div className="attention-queue-compact panel-inset">
        <p className="hint sm">
          <strong>{required.length} items need you</strong> — open Pipeline to review the queue.
        </p>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => {
            setActiveTab("pipeline");
            setPipelineSubTab("stage");
          }}
        >
          View all in Pipeline
        </button>
      </div>
    );
  }

  return (
    <section className="attention-queue-panel panel-inset" aria-label="Needs your attention">
      <div className="attention-queue-head">
        <button type="button" className="attention-queue-toggle" onClick={toggleCollapse}>
          <span className="attention-queue-title">
            Needs your attention ({required.length})
          </span>
          <span className="muted sm">{collapsed ? "Show" : "Hide"}</span>
        </button>
      </div>
      {!collapsed ? (
        <>
          <ol className="attention-queue-list">
            {required.map((item) => (
              <li key={`${item.kind}-${item.stageId}`} className={`attention-queue-row kind-${item.kind}`}>
                <SubstepRow
                  substep={attentionItemToSubstep(item)}
                  onClick={() => goToItem(item)}
                />
                <button
                  type="button"
                  className="btn primary sm attention-queue-primary"
                  onClick={() => goToItem(item)}
                >
                  {item.primaryLabel}
                </button>
              </li>
            ))}
          </ol>
          {optional.length > 0 ? (
            <details className="attention-queue-optional">
              <summary>Optional improvements ({optional.length})</summary>
              <ol className="attention-queue-list">
                {optional.map((item) => (
                  <li
                    key={`opt-${item.stageId}`}
                    className="attention-queue-row kind-optional attention-optional"
                  >
                    <div className="attention-queue-row-copy">
                      <p className="attention-queue-row-title">{item.title}</p>
                      <p className="hint sm">{item.message}</p>
                    </div>
                    <button
                      type="button"
                      className="btn ghost sm"
                      onClick={() => goToItem(item)}
                    >
                      View
                    </button>
                  </li>
                ))}
              </ol>
            </details>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
