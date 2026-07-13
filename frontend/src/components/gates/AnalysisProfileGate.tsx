import type { StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";
import { useState } from "react";
import { completeAnalysisProfile } from "../../utils/analysisProfileCheckpoint";

export function AnalysisProfileGate({ stage }: { stage: StageInfo }) {
  const { run, runId, refreshRun, showToast, setPipelineSubTab, advanceFromCheckpoint, setCheckpointBusy } = useApp();
  const [verifying, setVerifying] = useState(false);
  const ready = Boolean(run?.profile_ready_for_review);
  const verified = stage.status === "done" || Boolean(run?.profile_verified);
  const showDeliveryBlockHint = !verified;

  const verifyProfile = async () => {
    if (!runId || verifying) return;
    setVerifying(true);
    try {
      await completeAnalysisProfile({
        runId,
        verify: true,
        refreshRun,
        advanceFromCheckpoint,
        showToast,
        setBusy: setCheckpointBusy,
        successMessage: "Profile verified — you can continue.",
      });
    } finally {
      setVerifying(false);
    }
  };

  if (!ready && !verified) {
    return (
      <p className="muted">
        Understanding analysis has not finished yet. Run the analysis pipeline first —
        profile verification unlocks after AI populates themes and story fields.
      </p>
    );
  }

  return (
    <>
      <p className="gate-progress-subheader hint sm">
        {verified
          ? "Profile verified — continue when ready."
          : "Mark verified on Story Board when themes match your intent."}
      </p>
      <p className="hint">
        Review AI-generated themes, major questions, and style in the{" "}
        <strong>Story</strong> tab or <strong>Profile (JSON)</strong>. Mark verified when
        the profile matches your intent for this recording.
      </p>
      <p className="muted">
        {verified
          ? "Profile marked verified."
          : "Not verified yet — you can still edit before verifying."}
      </p>
      {showDeliveryBlockHint ? (
        <p className="hint">
          <strong>Podcast delivery</strong> (topic coverage and later) is blocked until
          you mark the profile verified.
        </p>
      ) : null}
      <div className="flow-choice profile-gate-actions">
        {!verified ? (
          <button
            type="button"
            className="btn primary sm"
            data-testid="mark-profile-verified-modal"
            disabled={verifying}
            onClick={() => void verifyProfile()}
          >
            {verifying ? (
              <>
                <span className="spinner-inline" aria-hidden /> Verifying…
              </>
            ) : (
              "Mark profile verified"
            )}
          </button>
        ) : null}
        <button
          type="button"
          className="btn ghost sm"
          disabled={verifying}
          onClick={() => setPipelineSubTab("profile")}
        >
          Open profile editor
        </button>
      </div>
    </>
  );
}
