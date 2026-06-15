from __future__ import annotations

from interview_mux.hardware_detect import detect_torch_device, is_apple_silicon, torch_index_url


def test_detect_torch_device_returns_known_label():
    dev = detect_torch_device()
    assert dev in {"cuda", "mps", "cpu"}


def test_torch_index_url_for_cpu():
    assert "pytorch.org" in torch_index_url("cpu")


def test_is_apple_silicon_bool():
    assert isinstance(is_apple_silicon(), bool)
