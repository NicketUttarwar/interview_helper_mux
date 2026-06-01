"""ElevenLabs HTTP API client (REST-first; no SDK required).

Canonical endpoints: docs/cross-cutting/elevenlabs-integration-guide.md
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
MUSIC_COMPOSE_PATH = "/music"
AUDIO_ISOLATION_PATH = "/audio-isolation"

# ElevenLabs Music API duration bounds (milliseconds).
MUSIC_LENGTH_MIN_MS = 3_000
MUSIC_LENGTH_MAX_MS = 600_000
DEFAULT_MUSIC_MODEL_ID = "music_v2"

_DEFAULT_BACKOFF_SECONDS = (5.0, 15.0, 45.0)


class ElevenLabsApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def _elevenlabs_cfg() -> dict[str, Any]:
    from interview_mux.config import merged_config

    return merged_config().get("elevenlabs") or {}


def _max_upload_bytes() -> int:
    return int(_elevenlabs_cfg().get("max_upload_bytes", 52_428_800))


def _request_timeout_sec() -> int:
    return int(_elevenlabs_cfg().get("request_timeout_sec", 120))


def _default_max_retries() -> int:
    return int(_elevenlabs_cfg().get("max_retries", 3))


def music_model_id() -> str:
    """Configured ElevenLabs Music model (default ``music_v2``)."""
    return str(_elevenlabs_cfg().get("music_model_id", DEFAULT_MUSIC_MODEL_ID))


def _music_model_id() -> str:
    return music_model_id()


def _force_instrumental_default() -> bool:
    return bool(_elevenlabs_cfg().get("force_instrumental", True))


def clamp_music_length_ms(duration_seconds: float) -> int:
    """Map plan duration to ElevenLabs Music API `music_length_ms` (3s–600s)."""
    ms = int(round(float(duration_seconds) * 1000))
    return max(MUSIC_LENGTH_MIN_MS, min(MUSIC_LENGTH_MAX_MS, ms))


def apply_prompt_influence_to_text(text: str, prompt_influence: float | None) -> str:
    """Music v2 has no `prompt_influence` field — encode adherence in prompt prose."""
    if prompt_influence is None:
        return text
    if prompt_influence >= 0.4:
        return (
            f"{text}\n\nFollow the description precisely with minimal improvisation; "
            "stay close to the specified texture, length, and mix role."
        )
    if prompt_influence <= 0.25:
        return (
            f"{text}\n\nAllow subtle variation while preserving the overall character "
            "and podcast-safe mix role."
        )
    return text


def generate_music(
    *,
    api_key: str,
    prompt: str,
    duration_seconds: float,
    model_id: str | None = None,
    force_instrumental: bool | None = None,
    prompt_influence: float | None = None,
    max_retries: int | None = None,
) -> bytes:
    """POST /v1/music — ElevenLabs Music (default model music_v2).

    Returns raw audio bytes from the response body. Requested `duration_seconds` below
    3s still uses a 3000ms API minimum; callers trim output when shorter beds/stingers
    are required.
    """
    if max_retries is None:
        max_retries = _default_max_retries()
    text = apply_prompt_influence_to_text(prompt, prompt_influence)
    payload: dict[str, Any] = {
        "prompt": text,
        "music_length_ms": clamp_music_length_ms(duration_seconds),
        "model_id": model_id or _music_model_id(),
        "force_instrumental": (
            _force_instrumental_default() if force_instrumental is None else force_instrumental
        ),
    }
    return _post_json_audio(
        api_key=api_key,
        path=MUSIC_COMPOSE_PATH,
        payload=payload,
        max_retries=max_retries,
    )


def generate_sound_effect(
    *,
    api_key: str,
    text: str,
    duration_seconds: float,
    prompt_influence: float | None = None,
    max_retries: int | None = None,
) -> bytes:
    """Generate podcast sound-design audio via ElevenLabs Music v2 (POST /v1/music)."""
    return generate_music(
        api_key=api_key,
        prompt=text,
        duration_seconds=duration_seconds,
        prompt_influence=prompt_influence,
        max_retries=max_retries,
    )


def isolate_audio(
    *,
    api_key: str,
    audio_bytes: bytes,
    filename: str = "audio.wav",
    max_retries: int | None = None,
) -> bytes:
    """POST /v1/audio-isolation (multipart) — returns isolated audio bytes."""
    if max_retries is None:
        max_retries = _default_max_retries()
    if len(audio_bytes) > _max_upload_bytes():
        raise ElevenLabsApiError(
            f"Audio upload {len(audio_bytes)} bytes exceeds elevenlabs.max_upload_bytes "
            f"({_max_upload_bytes()}); use chunked pre-clean or shorten source."
        )
    boundary = "----interviewmuxboundary7MA4YWxkTrZu0gW"
    body = _multipart_body(
        boundary=boundary,
        fields={},
        files={"audio": (filename, audio_bytes, "audio/wav")},
    )
    headers = {
        "xi-api-key": api_key,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    return _request_bytes(
        method="POST",
        path=AUDIO_ISOLATION_PATH,
        headers=headers,
        body=body,
        max_retries=max_retries,
    )


def _post_json_audio(
    *,
    api_key: str,
    path: str,
    payload: dict[str, Any],
    max_retries: int,
) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg, audio/wav, application/octet-stream",
    }
    return _request_bytes(
        method="POST",
        path=path,
        headers=headers,
        body=body,
        max_retries=max_retries,
    )


def _request_bytes(
    *,
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
    max_retries: int,
) -> bytes:
    url = f"{ELEVENLABS_API_BASE}{path}"
    attempt = 0
    while True:
        attempt += 1
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=_request_timeout_sec()) as resp:
                data = resp.read()
                if not data:
                    raise ElevenLabsApiError("empty response body", status=resp.status)
                return data
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            if exc.code in (401, 402):
                raise ElevenLabsApiError(
                    f"ElevenLabs HTTP {exc.code}",
                    status=exc.code,
                    body=err_body,
                ) from exc
            if exc.code == 429 or exc.code >= 500:
                if attempt <= max_retries:
                    delay = _DEFAULT_BACKOFF_SECONDS[min(attempt - 1, len(_DEFAULT_BACKOFF_SECONDS) - 1)]
                    if exc.code == 429:
                        delay = min(2.0**attempt, 32.0)
                    logger.warning(
                        "ElevenLabs %s %s; retry %s/%s in %.0fs",
                        method,
                        path,
                        attempt,
                        max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    continue
            raise ElevenLabsApiError(
                f"ElevenLabs HTTP {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc
        except urllib.error.URLError as exc:
            if attempt <= max_retries:
                delay = _DEFAULT_BACKOFF_SECONDS[min(attempt - 1, len(_DEFAULT_BACKOFF_SECONDS) - 1)]
                logger.warning("ElevenLabs network error; retry %s/%s", attempt, max_retries)
                time.sleep(delay)
                continue
            raise ElevenLabsApiError(f"ElevenLabs network error: {exc}") from exc


def _multipart_body(
    *,
    boundary: str,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> bytes:
    lines: list[bytes] = []
    crlf = b"\r\n"

    for name, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        lines.append(b"")
        lines.append(value.encode("utf-8"))

    for name, (filename, content, content_type) in files.items():
        lines.append(f"--{boundary}".encode())
        lines.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode()
        )
        lines.append(f"Content-Type: {content_type}".encode())
        lines.append(b"")
        lines.append(content)

    lines.append(f"--{boundary}--".encode())
    lines.append(b"")
    return crlf.join(lines)
