from __future__ import annotations

from interview_mux.elevenlabs_rest import (
    DEFAULT_MUSIC_MODEL_ID,
    apply_prompt_influence_to_text,
    clamp_music_length_ms,
    generate_music,
    generate_sound_effect,
    music_model_id,
)


def test_clamp_music_length_ms_minimum():
    assert clamp_music_length_ms(1.2) == 3000
    assert clamp_music_length_ms(3.0) == 3000


def test_clamp_music_length_ms_maximum():
    assert clamp_music_length_ms(700.0) == 600_000


def test_apply_prompt_influence_high_adds_strictness():
    out = apply_prompt_influence_to_text("Soft bed.", 0.45)
    assert "precisely" in out.lower()


def test_apply_prompt_influence_low_adds_variation_hint():
    out = apply_prompt_influence_to_text("Soft bed.", 0.2)
    assert "variation" in out.lower()


def test_apply_prompt_influence_mid_unchanged():
    text = "Soft bed."
    assert apply_prompt_influence_to_text(text, 0.35) == text


def test_music_model_id_default(monkeypatch):
    monkeypatch.delenv("INTERVIEW_MUX_CONFIG", raising=False)
    assert music_model_id() == DEFAULT_MUSIC_MODEL_ID


def test_generate_music_posts_music_v2_payload(monkeypatch):
    captured: dict = {}

    def fake_post_json_audio(**kwargs):
        captured.update(kwargs)
        return b"RIFF" + b"\x00" * 8

    monkeypatch.setattr(
        "interview_mux.elevenlabs_rest._post_json_audio",
        fake_post_json_audio,
    )
    monkeypatch.setattr(
        "interview_mux.elevenlabs_rest._music_model_id",
        lambda: "music_v2",
    )
    monkeypatch.setattr(
        "interview_mux.elevenlabs_rest._force_instrumental_default",
        lambda: True,
    )

    out = generate_music(
        api_key="k",
        prompt="Documentary ambient bed, no vocals.",
        duration_seconds=6.0,
        prompt_influence=0.3,
    )
    assert out.startswith(b"RIFF")
    assert captured["path"] == "/music"
    payload = captured["payload"]
    assert payload["model_id"] == "music_v2"
    assert payload["music_length_ms"] == 6000
    assert payload["force_instrumental"] is True
    assert "Documentary ambient bed" in payload["prompt"]


def test_generate_sound_effect_delegates_to_music(monkeypatch):
    calls: list[dict] = []

    def fake_music(**kwargs):
        calls.append(kwargs)
        return b"\x00"

    monkeypatch.setattr("interview_mux.elevenlabs_rest.generate_music", fake_music)
    generate_sound_effect(
        api_key="k",
        text="stinger",
        duration_seconds=1.5,
        prompt_influence=0.4,
    )
    assert calls[0]["prompt"] == "stinger"
    assert calls[0]["duration_seconds"] == 1.5
