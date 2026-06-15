"""Hardware detection for local PyTorch venv bootstraps."""

from __future__ import annotations

import platform
import shutil
import subprocess


def is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def has_nvidia_gpu() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        proc = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def detect_torch_device() -> str:
    """Return cuda, mps, or cpu for PyTorch wheel selection."""
    if has_nvidia_gpu():
        return "cuda"
    if is_apple_silicon():
        return "mps"
    return "cpu"


def torch_index_url(device: str | None = None) -> str:
    dev = device or detect_torch_device()
    if dev == "cuda":
        return "https://download.pytorch.org/whl/cu124"
    if dev == "mps":
        return "https://download.pytorch.org/whl/cpu"
    return "https://download.pytorch.org/whl/cpu"
