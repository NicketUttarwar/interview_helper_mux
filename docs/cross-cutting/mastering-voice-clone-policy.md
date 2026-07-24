# Mastering voice-clone policy

Authorization rules for synthetic voice in the master. Canon: [mastering-quality-hardening.md](./mastering-quality-hardening.md).

**Principle:** *least-spoken* is an editorial rule about who may be voiced. It is **not** authorization. Cloning requires explicit consent, an approved reference, and a declared usage scope.

Artifact: `mastering/voice_clone_audit.json` · Gates: [`gap_vo_gates.py`](../../src/interview_mux/gap_vo_gates.py)

---

## Absolute bans

| Ban | Rationale |
|-----|-----------|
| **No guest / content-speaker cloning, ever** | The guest's words are the product; synthesizing them destroys the record |
| **No cross-run voice reuse without re-consent** | Consent is per-run, per-speaker |
| **No clone of an unidentified speaker** | Cannot consent on behalf of an unknown person |

These are not configurable. A plan requesting a content-speaker clone fails feasibility with `pickup_voice_authorized`, in every mode including `off`.

---

## Authorization chain

A clone is authorized only when **all four** hold:

1. **Eligibility** — speaker is the pickup-eligible frame-role speaker (`pickup_eligible_speaker_id`)
2. **Reference approved** — `understanding/voice_reference/{speaker_id}.json` has `approved: true`
3. **Consent recorded** — explicit operator consent with actor and UTC timestamp
4. **Scope permits the use** — the requested use is in the granted scope list

Missing any one → hard fail. Cold-open kinds `vo_clone_only` / `vo_clone_plus_sfx` and any synthesized VO line are blocked.

---

## Consent record

Stored in `run_meta.json` and mirrored into the audit artifact:

```json
{
  "voice_clone_consent": {
    "speaker_id": "spk_1",
    "granted": true,
    "granted_by": "operator",
    "granted_at": "2026-07-24T18:22:04Z",
    "scopes": ["cold_open", "bridges", "outro"],
    "reference_path": "understanding/voice_reference/spk_1.json",
    "disclosure": "none",
    "revoked_at": null
  }
}
```

### Scopes

| Scope | Covers |
|-------|--------|
| `cold_open` | Synthetic cold-open narration |
| `bridges` | Inter-segment VO bridges and framing questions |
| `outro` | Closing narration |

Scopes are granted individually. Granting `bridges` does not grant `cold_open`.

### Disclosure

| Value | Meaning |
|-------|---------|
| `none` | No disclosure rendered (default; host voicing own words) |
| `show_notes` | Disclosure text emitted into delivery metadata |
| `in_audio` | Spoken disclosure line placed in the outro |

Disclosure choice is recorded in the audit trail regardless of value.

### Revocation

Setting `revoked_at` invalidates the consent immediately. Any stage that would use the clone re-checks at runtime; already-rendered clone audio must be invalidated with the stages that produced it.

---

## Audit trail

`mastering/voice_clone_audit.json` records every synthetic utterance:

- `line_id`, source text, and the artifact that authored it
- `speaker_id` and the consent record hash
- Scope claimed for the use
- Synthesis path (Chatterbox / recorded / fallback) and output WAV path
- Timestamp

The audit is the answer to "which words in this master were not actually spoken?" It must be complete even when consent checks are advisory.

---

## Interaction with `record` delivery

When `gap_vo_delivery = record`, the operator records the line themselves. No clone occurs, so consent is not required — but the audit still logs the line as **operator-recorded VO** so the provenance question stays answerable.

---

## Operator surface

Extends the existing G-VoiceRef gate:

- Approve reference sample (existing)
- **Grant clone consent** with scope checkboxes (new)
- Choose disclosure (new)
- Revoke (new)

Payload extends `gap_gate_payload()` with `voice_clone_consent`, `voice_clone_scopes`, and `voice_clone_consent_pending`.

---

## Config

```
mastering.quality_hardening.voice_clone.mode            off|advisory|authoritative
mastering.quality_hardening.voice_clone.default_scopes  []
mastering.quality_hardening.voice_clone.require_disclosure  false
```

`mode` never relaxes the guest-clone ban.
