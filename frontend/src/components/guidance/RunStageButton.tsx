import { useApp } from "../../context/AppContext";

interface Props {
  stageId: string;
  stepNumber?: number | null;
  disabled?: boolean;
}

export function RunStageButton({ stageId, stepNumber, disabled }: Props) {
  const { runNextStage, selectStage, jobRunning } = useApp();

  return (
    <button
      type="button"
      className="btn primary sm"
      disabled={disabled || jobRunning}
      onClick={() => {
        void selectStage(stageId);
        void runNextStage();
      }}
    >
      {jobRunning ? "Running…" : stepNumber ? `Run step ${stepNumber}` : "Run this step"}
    </button>
  );
}
