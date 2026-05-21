#!/usr/bin/env python3
"""Step 2 gate: verify Python packages after ``pip install -r requirements.txt``."""

from __future__ import annotations

import sys


def main() -> int:
    print("=== Step 2: Python package verification ===")
    print(f"python: {sys.version.split()[0]} @ {sys.executable}")

    required = [
        ("mux_secrets", "mux_secrets"),
        ("mux_store", "mux_store"),
        ("pipeline", "pipeline"),
        ("pydantic", "pydantic"),
        ("numpy", "numpy"),
        ("pydub", "pydub"),
        ("faster_whisper", "faster_whisper"),
        ("pyloudnorm", "pyloudnorm"),
        ("soundfile", "soundfile"),
        ("openai", "openai"),
        ("elevenlabs", "elevenlabs"),
    ]
    failed: list[str] = []
    for label, mod in required:
        try:
            __import__(mod)
            print(f"  OK   {label}")
        except ImportError as e:
            print(f"  FAIL {label}: {e}")
            failed.append(label)

    try:
        from aws_mux import run_aws_cli, sts_get_caller_identity  # noqa: F401

        print("  OK   aws_mux (CLI, no boto3 session)")
    except Exception as e:
        print(f"  FAIL aws_mux: {e}")
        failed.append("aws_mux")

    try:
        import boto3  # noqa: F401

        print("  WARN boto3 installed (not required; aws_mux uses CLI only)")
    except ImportError:
        print("  OK   boto3 not installed (expected)")

    try:
        from pipeline.common import repo_root

        print(f"  OK   repo_root={repo_root()}")
    except Exception as e:
        print(f"  FAIL pipeline.common: {e}")
        failed.append("pipeline.common")

    if sys.version_info < (3, 12):
        print(f"  FAIL python_version: need 3.12+, got {sys.version.split()[0]}")
        failed.append("python_version")
    elif sys.version_info >= (3, 14):
        print(f"  FAIL python_version: need <3.14, got {sys.version.split()[0]}")
        failed.append("python_version")
    else:
        print(f"  OK   python {sys.version_info.major}.{sys.version_info.minor} (3.12.x canonical)")

    import os
    import platform

    host = os.uname().machine
    py_arch = platform.machine()
    if host == "arm64" and py_arch == "x86_64":
        print(
            "  FAIL python_arch: venv is x86_64 under Rosetta — "
            "rebuild with export PYTHON=/opt/homebrew/bin/python3.12 && ./scripts/bootstrap_venv.sh"
        )
        failed.append("python_arch")
    elif host == py_arch:
        print(f"  OK   python arch matches host ({host})")
    else:
        print(f"  WARN python arch {py_arch} vs host {host}")

    print("=== Step 2 complete ===")
    if failed:
        print("Install project + dependencies in the active venv:")
        print("  ./scripts/bootstrap_venv.sh")
        print("  # or: pip install -r requirements.txt")
        return 1
    print("PASS — proceed to Step 3: python tools/check_env.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
