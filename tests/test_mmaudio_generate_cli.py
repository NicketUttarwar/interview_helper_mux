"""CLI tests for tools/mmaudio_generate.py argument wiring."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_mmaudio_generate_calls_native_with_cfg():
    from tools.mmaudio_generate import main

    out = Path("/tmp/test_mmaudio_out.wav")
    with patch("tools.mmaudio_generate._native_generate") as gen:
        with patch(
            "sys.argv",
            [
                "mmaudio_generate.py",
                "--prompt",
                "soft bed",
                "--negative-prompt",
                "no vocals",
                "--duration",
                "4.0",
                "--cfg-strength",
                "4.2",
                "--num-steps",
                "20",
                "--seed",
                "99",
                "--output-wav",
                str(out),
            ],
        ):
            rc = main()
    assert rc == 0
    gen.assert_called_once()
    kwargs = gen.call_args.kwargs
    assert kwargs["prompt"] == "soft bed"
    assert kwargs["negative_prompt"] == "no vocals"
    assert kwargs["cfg_strength"] == 4.2
    assert kwargs["num_steps"] == 20
    assert kwargs["seed"] == 99
