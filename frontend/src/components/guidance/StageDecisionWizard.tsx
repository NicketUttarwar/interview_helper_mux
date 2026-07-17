import { useEffect, useMemo, useState } from "react";
import type { StageInfo } from "../../types";
import { useStageDecisions } from "../../hooks/useStageDecisions";

interface Props {
  stage: StageInfo;
}

function defaultChoice(
  kind: string,
  options: { label: string; value: unknown }[],
  recommended: unknown,
): unknown {
  if (recommended !== undefined && recommended !== null) return recommended;
  if (kind === "acknowledge_warning") return "acknowledge";
  if (options.length === 1) return options[0].value;
  return options[0]?.value;
}

export function StageDecisionWizard({ stage }: Props) {
  const {
    loading,
    busy,
    current,
    openCount,
    decisionIndex,
    readyForReview,
    resolveCurrent,
  } = useStageDecisions(stage.id);

  const options = current?.options ?? [];
  const [selectedIndex, setSelectedIndex] = useState(0);

  useEffect(() => {
    if (!current) {
      setSelectedIndex(0);
      return;
    }
    if (current.recommended !== undefined && current.recommended !== null) {
      const recIdx = options.findIndex(
        (opt) => JSON.stringify(opt.value) === JSON.stringify(current.recommended),
      );
      if (recIdx >= 0) {
        setSelectedIndex(recIdx);
        return;
      }
    }
    setSelectedIndex(0);
  }, [current?.id, current?.recommended, options]);

  const progressLabel = useMemo(() => {
    if (!current || openCount <= 1) return null;
    return `Decision ${decisionIndex} of ${openCount}`;
  }, [current, openCount, decisionIndex]);

  if (loading && !current && openCount === 0) {
    return <p className="hint sm">Loading decisions…</p>;
  }

  if (readyForReview && !current) {
    return (
      <p className="hint sm" data-testid="stage-decision-wizard-complete">
        Autopilot cleared all decisions — review staged outputs below.
      </p>
    );
  }

  if (!current) {
    return null;
  }

  const isIssueChoice = current.kind === "issue_choice";
  const primaryLabel =
    current.kind === "acknowledge_warning"
      ? "Continue to review"
      : current.kind === "propagation" || current.kind === "upstream_rerun"
        ? options[0]?.label ?? "Apply"
        : "Apply choice";

  const onPrimary = () => {
    const picked =
      options[selectedIndex]?.value ??
      defaultChoice(current.kind, options, current.recommended);
    void resolveCurrent(picked);
  };

  return (
    <div className="stage-decision-panel stage-decision-wizard" data-testid="stage-decision-wizard">
      {progressLabel ? (
        <p className="hint sm stage-decision-progress">{progressLabel}</p>
      ) : null}
      <h3 className="stage-decision-headline">{current.headline}</h3>
      <p className="hint sm stage-decision-detail">{current.detail}</p>
      {current.kind === "acknowledge_warning" ? (
        <p className="hint sm">
          Autopilot repaired what it could automatically. Confirm you have reviewed the note above,
          then continue to staged outputs.
        </p>
      ) : null}

      {isIssueChoice && options.length > 1 ? (
        <label className="stage-decision-select-wrap">
          <span className="sr-only">Choose how to resolve this issue</span>
          <select
            className="stage-decision-select"
            value={selectedIndex}
            disabled={busy}
            onChange={(e) => setSelectedIndex(Number(e.target.value))}
            data-testid="stage-decision-select"
          >
            {options.map((opt, idx) => (
              <option key={`${opt.label}-${idx}`} value={idx}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <div className="stage-decision-actions">
        <button
          type="button"
          className="btn primary"
          disabled={busy || (isIssueChoice && options.length > 1 && selectedIndex < 0)}
          onClick={onPrimary}
          data-testid="stage-decision-apply"
        >
          {primaryLabel}
        </button>
        {current.kind === "propagation" || current.kind === "upstream_rerun" ? (
          <button
            type="button"
            className="btn ghost"
            disabled={busy}
            onClick={() =>
              void resolveCurrent(
                current.kind === "propagation"
                  ? { action: "skip_propagation" }
                  : "skip",
              )
            }
            data-testid="stage-decision-skip"
          >
            Skip — I&apos;ll fix manually
          </button>
        ) : null}
      </div>
    </div>
  );
}
