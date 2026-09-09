"""Constitutional precedence for seat / omit / bind decisions (cross-wave).

Order (highest first):
1. Required orientation — never strip
2. Explicit operator_override skips
3. Sanitary seats <= rendered WAVs when floor met (clamp wins)
4. Pass B published seats after clamp
5. Hosted framing ensure only when floor unmet and clamp would not undo
6. Bind freshness (line_vo_wav_fresh) — mismatch => delete+regenerate
7. Synth regenerate after seats sanitary + text final
8. Ledger mirrors gap/seats — never invents seat expansion
"""

from __future__ import annotations

PRECEDENCE_ORDER: tuple[str, ...] = (
    "required_orientation",
    "operator_override_skip",
    "clamp_seats_to_wavs",
    "pass_b_seats",
    "hosted_framing_ensure",
    "bind_freshness",
    "synth_regenerate",
    "ledger_mirrors",
)

# Gap sanitize (W1) may NOT mutate these authorities — owned by air_contract (W3).
GAP_SANITIZE_FORBIDDEN_MUTATIONS: frozenset[str] = frozenset(
    {
        "vo_seats",
        "omit_ledger_entries",
        "clamp_seats",
        "ensure_hosted_framing",
    }
)
