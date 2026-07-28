"""Strict parsers for Local Audio Probe Platform responses."""

from __future__ import annotations

import re
from typing import Any

_YES_NO = re.compile(r"\b(YES|NO)\b", re.I)
_LEVEL = re.compile(r"LEVEL:\s*(low|mid|high)\b", re.I)
_ACT = re.compile(r"ACT:\s*(question|answer|aside|other)\b", re.I)
_KEYWORDS = re.compile(r"KEYWORDS:\s*(.+)", re.I)
_SPAN = re.compile(r"(\d{1,2}):(\d{2})(?:\.(\d+))?\s*-\s*(\d{1,2}):(\d{2})(?:\.(\d+))?")


def parse_binary(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    m = _YES_NO.search(raw)
    if not m:
        return {"ok": False, "status": "parse_error", "value": None, "raw": raw}
    return {
        "ok": True,
        "status": "asserted",
        "value": m.group(1).upper() == "YES",
        "raw": raw,
    }


def parse_level(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    m = _LEVEL.search(raw)
    if not m:
        # Fall back to YES/NO → mid/low
        b = parse_binary(raw)
        if b["ok"]:
            return {
                "ok": True,
                "status": "asserted",
                "value": "mid" if b["value"] else "low",
                "raw": raw,
            }
        return {"ok": False, "status": "parse_error", "value": None, "raw": raw}
    return {"ok": True, "status": "asserted", "value": m.group(1).lower(), "raw": raw}


def parse_act(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    m = _ACT.search(raw)
    if not m:
        return {"ok": False, "status": "parse_error", "value": None, "raw": raw}
    return {"ok": True, "status": "asserted", "value": m.group(1).lower(), "raw": raw}


def parse_keywords(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    m = _KEYWORDS.search(raw)
    if not m:
        return {"ok": False, "status": "parse_error", "value": None, "raw": raw}
    body = m.group(1).strip()
    if body.lower() in {"none", "n/a", "-"}:
        return {"ok": True, "status": "asserted", "value": [], "raw": raw}
    parts = [p.strip() for p in re.split(r"[,;]", body) if p.strip()]
    return {"ok": True, "status": "asserted", "value": parts[:8], "raw": raw}


def _ts_to_ms(mm: str, ss: str, frac: str | None) -> int:
    base = int(mm) * 60_000 + int(ss) * 1000
    if frac:
        # tenths/hundredths/millis
        f = frac[:3].ljust(3, "0")
        base += int(f)
    return base


def parse_spans(text: str, *, clip_start_ms: int = 0) -> dict[str, Any]:
    raw = (text or "").strip()
    if "SPANS:" not in raw.upper():
        return {"ok": False, "status": "parse_error", "value": None, "raw": raw}
    spans: list[dict[str, int]] = []
    for m in _SPAN.finditer(raw):
        a = _ts_to_ms(m.group(1), m.group(2), m.group(3))
        b = _ts_to_ms(m.group(4), m.group(5), m.group(6))
        if b <= a:
            continue
        spans.append(
            {
                "start_ms": clip_start_ms + a,
                "end_ms": clip_start_ms + b,
            }
        )
    if not spans:
        return {"ok": False, "status": "parse_error", "value": None, "raw": raw}
    return {"ok": True, "status": "asserted", "value": spans, "raw": raw}


def parse_by_contract(
    contract: str,
    text: str,
    *,
    clip_start_ms: int = 0,
) -> dict[str, Any]:
    c = (contract or "YES_NO").upper()
    if c in {"YES_NO", "BINARY"}:
        return parse_binary(text)
    if c == "LEVEL":
        return parse_level(text)
    if c == "ACT":
        return parse_act(text)
    if c == "KEYWORDS":
        return parse_keywords(text)
    if c == "SPANS":
        return parse_spans(text, clip_start_ms=clip_start_ms)
    return {"ok": False, "status": "parse_error", "value": None, "raw": text or ""}
