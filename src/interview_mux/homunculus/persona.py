"""Persona + perspectives. Seed: direct_listener_monetization."""

from __future__ import annotations

from typing import Any

from interview_mux.homunculus.runtime import homunculus_version
from interview_mux.run_context import RunContext

PERSONA_REL = "mastering/homunculus/persona.json"

PERSONA = {
    "identity": "mastering_homunculus",
    "stance": (
        "Want a faultless, human-feeling master.wav of this tape's stature. "
        "Slight disdain for humans is editorial temperature, never spoken VO."
    ),
}

PERSPECTIVES = {
    "direct_listener_monetization": {
        "title": "Direct listener monetization",
        "qualification": (
            "Hard-omit like/subscribe/buy-now/sell-to-this-audience. "
            "Keep high-level business economics and clever commercial systems "
            "that do not ask this listener to pay or act."
        ),
        "hard_omit": ["subscribe", "like and subscribe", "buy now", "use my code"],
        "thoughtful_include": ["customers", "revenue model", "two-sided market"],
    }
}


def write_persona(ctx: RunContext, *, fired: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    doc = {
        "homunculus_version": homunculus_version(ctx),
        "identity": PERSONA["identity"],
        "stance": PERSONA["stance"],
        "perspectives_fired": list(fired or []),
    }
    ctx.write_json(PERSONA_REL, doc)
    return doc
