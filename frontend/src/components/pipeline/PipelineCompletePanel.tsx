import { useApp } from "../../context/AppContext";
import {
  isPipelineComplete,
  resolveFinalOutputAbsolutePath,
} from "../../utils/pipelineAutopilot";

export function PipelineCompletePanel() {
  const { run, showToast } = useApp();

  if (!run || !isPipelineComplete(run)) {
    return null;
  }

  const outputPath = resolveFinalOutputAbsolutePath(run);
  const workingDir = run.working_dir?.replace(/\/$/, "") || null;

  const copyPath = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path);
      showToast("Path copied to clipboard.", "success");
    } catch {
      showToast("Could not copy path — select and copy manually.", "warning");
    }
  };

  return (
    <div className="panel pipeline-complete-panel" data-testid="pipeline-complete-panel">
      <div className="pipeline-complete-hero">
        <p className="pipeline-complete-kicker">Pipeline finished</p>
        <h2>You have completed your podcast</h2>
        <p className="hint">
          Every automated step in this run finished. Your deliverable is ready on disk.
        </p>
      </div>

      {outputPath ? (
        <section className="pipeline-complete-output">
          <h3>Final output file</h3>
          <div className="pipeline-complete-path-row">
            <code className="pipeline-complete-path">{outputPath}</code>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => void copyPath(outputPath)}
            >
              Copy path
            </button>
          </div>
        </section>
      ) : null}

      {workingDir ? (
        <p className="hint sm pipeline-complete-workdir">
          Run folder: <code>{workingDir}</code>
        </p>
      ) : null}
    </div>
  );
}
