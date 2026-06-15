"""Warn when runs retain legacy ElevenLabs stage markers from before MMAudio migration."""

from __future__ import annotations

LEGACY_SFX_STAGE_IDS: tuple[str, ...] = (
    "elevenlabs_prompt_craft",
    "elevenlabs_sfx_flow1",
    "elevenlabs_sfx_flow2",
)

LEGACY_SFX_ARTIFACT = "sound_design/elevenlabs_prompts.json"


def legacy_sfx_warnings(ctx) -> list[str]:
    """Return human-readable warnings for legacy ElevenLabs stage/artifact markers."""
    warnings: list[str] = []
    done = [stage for stage in LEGACY_SFX_STAGE_IDS if ctx.is_done(stage)]
    if done:
        warnings.append(
            "Legacy ElevenLabs stage markers detected ("
            + ", ".join(done)
            + "). Re-run from sfx_prompt_craft after approving sound_design/sfx_prompts.json."
        )
    if ctx.artifact_exists(LEGACY_SFX_ARTIFACT) and not ctx.artifact_exists(
        "sound_design/sfx_prompts.json"
    ):
        warnings.append(
            "Legacy artifact sound_design/elevenlabs_prompts.json present without sfx_prompts.json — "
            "migrate prompts (sfx_prompt field) or re-run sfx_prompt_craft."
        )
    return warnings


def maybe_log_legacy_sfx_warnings(ctx) -> None:
    for message in legacy_sfx_warnings(ctx):
        ctx.log(message, level="warning", stage="migration")
