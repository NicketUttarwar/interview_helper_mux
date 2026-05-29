import type { StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";
import { PrecleanOfferCard } from "./PrecleanOfferCard";
import { resolvePrecleanOffer } from "../../utils/preclean";

export function AnalysisProfileGate({ stage }: { stage: StageInfo }) {
  const { run } = useApp();
  const verified = stage.status === "done";
  const flow1Block =
    run?.selected_flow === "flow1" && run?.profile_gate_pending;
  const offer = resolvePrecleanOffer(stage);

  return (
    <>
      <p className="hint">
        Review themes, major questions, and style in the{" "}
        <strong>Interview profile</strong> panel below. Mark verified when the profile
        matches your intent for this recording.
      </p>
      <p className="muted">
        {verified
          ? "Profile marked verified."
          : "Not verified yet — AI stages still treat profile as draft."}
      </p>
      {flow1Block ? (
        <p className="hint">
          <strong>Flow 1 extended</strong> (topic coverage and later) is blocked until
          you mark the profile verified.
        </p>
      ) : null}
      {offer ? <PrecleanOfferCard stage={stage} offer={offer} /> : null}
    </>
  );
}
