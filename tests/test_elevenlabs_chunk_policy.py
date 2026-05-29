from interview_mux.elevenlabs_rest import ElevenLabsApiError, _max_upload_bytes, isolate_audio


def test_max_upload_bytes_default():
    assert _max_upload_bytes() > 0


def test_isolate_rejects_oversized_without_chunking():
    huge = b"x" * (_max_upload_bytes() + 1)
    try:
        isolate_audio(api_key="test", audio_bytes=huge)
        assert False, "expected ElevenLabsApiError"
    except ElevenLabsApiError as exc:
        assert "exceeds" in str(exc).lower()
