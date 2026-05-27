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
SOUND_GENERATION_PATH = "/sound-generation"
AUDIO_ISOLATION_PATH = "/audio-isolation"

_DEFAULT_BACKOFF_SECONDS = (5.0, 15.0, 45.0)


class ElevenLabsApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def generate_sound_effect(
    *,
    api_key: str,
    text: str,
    duration_seconds: float,
    prompt_influence: float | None = None,
    max_retries: int = 3,
) -> bytes:
    """POST /v1/sound-generation — returns raw audio bytes from response body."""
    payload: dict[str, Any] = {
        "text": text,
        "duration_seconds": duration_seconds,
    }
    if prompt_influence is not None:
        payload["prompt_influence"] = prompt_influence

    return _post_json_audio(
        api_key=api_key,
        path=SOUND_GENERATION_PATH,
        payload=payload,
        max_retries=max_retries,
    )


def isolate_audio(
    *,
    api_key: str,
    audio_bytes: bytes,
    filename: str = "audio.wav",
    max_retries: int = 3,
) -> bytes:
    """POST /v1/audio-isolation (multipart) — returns isolated audio bytes."""
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
            with urllib.request.urlopen(req, timeout=120) as resp:
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
