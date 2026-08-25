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
            "Hard-omit like/subscribe/buy-now/sell-to-this-audience and sponsor "
            "bumpers (sponsored by / presented by / brought to you by / powered by / "
            "in partnership with). "
            "Keep high-level business economics and clever commercial systems "
            "that do not ask this listener to pay or act."
        ),
        "hard_omit": [
            "like and subscribe",
            "go subscribe",
            "please subscribe",
            "subscribe to my",
            "subscribe to our",
            "subscribe to this",
            "subscribe to the show",
            "hit the like button",
            "comments section",
            "our sponsor",
            "thanks again to our sponsor",
            "thanks to our sponsor",
            "audio-only version of the show",
            "audio only version of the show",
            "buy now",
            "use my code",
            "sponsored by",
            "presented by",
            "brought to you by",
            "powered by",
            "in partnership with",
            "podcast produced by",
            "production support from",
            "music for this podcast",
        ],
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
