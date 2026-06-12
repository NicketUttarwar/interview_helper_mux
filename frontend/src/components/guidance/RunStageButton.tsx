import { useApp } from "../../context/AppContext";
import { isJobActivelyRunning } from "../../utils/jobStatus";

interface Props {
  stageId: string;
  stepNumber?: number | null;
  disabled?: boolean;
}

export function RunStageButton({ stageId, stepNumber, disabled }: Props) {
  const { runNextStage, selectStage, jobRunning, run } = useApp();
  const jobActive = isJobActivelyRunning(run?.job) || jobRunning;

  return (
    <button
      type="button"
      className="btn primary sm"
      disabled={disabled || jobActive}
      onClick={() => {
        void selectStage(stageId);
        void runNextStage();
      }}
    >
      {jobActive ? "Running…" : stepNumber ? `Run step ${stepNumber}` : "Run this step"}
    </button>
  );
}
