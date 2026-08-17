"""Speaker dossier from transcribe / roles / intros. Names only if on tape."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext

DOSSIER_REL = "mastering/homunculus/speaker_dossier.json"
_INTRO = re.compile(
    r"\b(?:i['’]?m|i am|my name is|with me (?:today )?is|joining (?:us|me))\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    re.I,
)


def build_speaker_dossier(ctx: RunContext) -> dict[str, Any]:
    speakers = {}
    if ctx.artifact_exists("understanding/speakers.json"):
        raw = ctx.read_json("understanding/speakers.json")
        if isinstance(raw, dict):
            speakers = raw.get("speakers") or raw
    text = ""
    for rel in ("ingest/transcript.json", "transcripts/index.json"):
        if ctx.artifact_exists(rel):
            blob = ctx.read_json(rel)
            if isinstance(blob, dict):
                text = str(blob.get("text") or "")
            break
    intros = [{"quote": m.group(0), "name": m.group(1)} for m in _INTRO.finditer(text or "")]
    labels: dict[str, str] = {}
    if isinstance(speakers, dict):
        for sid, row in speakers.items():
            if not isinstance(row, dict):
                continue
            label = row.get("label") or row.get("display_name")
            if label:
                labels[str(sid)] = str(label)
    thin = not labels and not intros
    dossier = {
        "speakers": speakers if isinstance(speakers, dict) else {},
        "labels": labels,
        "intro_spans": intros,
        "speaker_identity_thin": thin,
        "invented_names": False,
    }
    ctx.write_json(DOSSIER_REL, dossier)
    if thin:
        from interview_mux.homunculus.issues import emit_issue

        emit_issue(
            ctx,
            kind="speaker_identity_thin",
            source="speakers",
            evidence={"intros": intros},
        )
    return dossier
