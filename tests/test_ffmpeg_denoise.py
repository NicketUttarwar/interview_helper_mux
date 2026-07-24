from pathlib import Path

import pytest

from interview_mux.ffmpeg_denoise import denoise_wav


def test_denoise_wav_builds_bounded_filter_chain(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.wav"
    output = tmp_path / "clean.wav"
    source.write_bytes(b"RIFF" + b"\x00" * 64)
    seen: list[str] = []

    def fake_run(command, **kwargs):
        seen.extend(command)
        Path(command[-1]).write_bytes(b"RIFF" + b"\x00" * 64)

    monkeypatch.setattr("interview_mux.ffmpeg_denoise.run_command", fake_run)

    assert denoise_wav(source, output) == output
    assert output.is_file()
    filter_chain = seen[seen.index("-af") + 1]
    assert filter_chain == "highpass=f=80,lowpass=f=12000,afftdn=nr=12"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"highpass_hz": 10},
        {"highpass_hz": 1000, "lowpass_hz": 500},
        {"noise_reduction_db": 100},
    ],
)
def test_denoise_wav_rejects_unsafe_parameters(tmp_path, kwargs) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"RIFF" + b"\x00" * 64)
    with pytest.raises(ValueError):
        denoise_wav(source, tmp_path / "clean.wav", **kwargs)
