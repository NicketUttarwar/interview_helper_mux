"""Chatterbox CLI must call from_pretrained(device) only (0.1.x API)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "chatterbox_generate.py"


def _load_chatterbox_main():
    spec = importlib.util.spec_from_file_location("chatterbox_generate_under_test", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_chatterbox_from_pretrained_device_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF" + b"\x00" * 64)
    out = tmp_path / "out.wav"

    fake_torch = MagicMock()
    fake_torch.backends.mps.is_available.return_value = False
    fake_torchaudio = MagicMock()
    fake_model = MagicMock()
    fake_model.sr = 24000
    fake_wav = MagicMock()
    fake_wav.ndim = 1
    fake_wav.unsqueeze.return_value.cpu.return_value = fake_wav
    fake_model.generate.return_value = fake_wav
    fake_tts = MagicMock()
    fake_tts.from_pretrained.return_value = fake_model

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "torchaudio", fake_torchaudio)
    chatterbox_pkg = MagicMock()
    chatterbox_tts = MagicMock()
    chatterbox_tts.ChatterboxTTS = fake_tts
    monkeypatch.setitem(sys.modules, "chatterbox", chatterbox_pkg)
    monkeypatch.setitem(sys.modules, "chatterbox.tts", chatterbox_tts)
    fake_perth = MagicMock()
    fake_perth.PerthImplicitWatermarker = MagicMock()
    monkeypatch.setitem(sys.modules, "perth", fake_perth)
    monkeypatch.setitem(sys.modules, "perth.dummy_watermarker", MagicMock())

    mod = _load_chatterbox_main()
    payload = {
        "text": "Hello smoke.",
        "ref_audio": str(ref),
        "out_wav": str(out),
        "model_id": "ResembleAI/chatterbox",
    }
    monkeypatch.setattr(sys, "stdin", MagicMock(read=lambda: json.dumps(payload)))
    printed: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: printed.append(a[0] if a else ""))

    rc = mod.main()
    assert rc == 0, printed
    fake_tts.from_pretrained.assert_called_once_with("cpu")
    args = fake_tts.from_pretrained.call_args.args
    assert args == ("cpu",)
    body = json.loads(printed[-1])
    assert body.get("ok") is True
    assert body.get("model_id") == "ResembleAI/chatterbox"


def test_chatterbox_errors_emit_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_chatterbox_main()
    monkeypatch.setattr(sys, "stdin", MagicMock(read=lambda: json.dumps({"text": ""})))
    printed: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: printed.append(a[0] if a else ""))
    rc = mod.main()
    assert rc == 1
    body = json.loads(printed[-1])
    assert body.get("ok") is False
    assert "text" in str(body.get("error") or "").lower()
