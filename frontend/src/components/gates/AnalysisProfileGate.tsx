import { api } from "../../api/client";
import type { StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";

export function AnalysisProfileGate({ stage }: { stage: StageInfo }) {
  const { run, runId, refreshRun, showToast, setPipelineSubTab, advanceFromCheckpoint } = useApp();
  const ready = Boolean(run?.profile_ready_for_review);
  const verified = stage.status === "done" || Boolean(run?.profile_verified);
  const flow1Block =
    run?.selected_flow === "flow1" && run?.profile_gate_pending;

  const verifyProfile = async () => {
    if (!runId) return;
    try {
      await api(`/api/runs/${runId}/analysis-profile/verify`, { method: "POST" });
      showToast("Profile verified — you can continue.");
      await refreshRun();
      await advanceFromCheckpoint();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Could not verify profile");
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
      {flow1Block ? (
        <p className="hint">
          <strong>Flow 1 extended</strong> (topic coverage and later) is blocked until
          you mark the profile verified.
        </p>
      ) : null}
      <div className="flow-choice profile-gate-actions">
        {!verified ? (
          <button
            type="button"
            className="btn primary sm"
            data-testid="mark-profile-verified-modal"
            onClick={() => void verifyProfile()}
          >
            Mark profile verified
          </button>
        ) : null}
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => setPipelineSubTab("profile")}
        >
          Open profile editor
        </button>
      </div>
    </>
  );
}
