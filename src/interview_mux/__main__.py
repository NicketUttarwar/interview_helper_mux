"""python -m interview_mux — default: full pipeline (analysis → G1 → flow)."""

from interview_mux.cli import app
from interview_mux.process_logging import configure_process_logging

if __name__ == "__main__":
    configure_process_logging()
    app(prog_name="interview-mux")
