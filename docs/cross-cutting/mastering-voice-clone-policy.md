# Mastering voice-clone policy

Authorization rules for synthetic voice in the master. Canon: [mastering-quality-hardening.md](./mastering-quality-hardening.md) · Narrative: [narrative-mode-and-montage.md](./narrative-mode-and-montage.md).

**Principle:** Prefer **pickup / least-spoken** for new VO when an interviewer/frame speaker is clear. Consent + approved reference + scope authorize cloning. **Any speaker on the recording is fair game when needed** (including guests) — ideally avoid non-pickup. **Monologue / no clear interviewer:** clone the sole or primary on-tape speaker for inserts (`understanding/speaker_delivery_plan.json`). Never invent unspoken interview dialogue; never clone people not on the tape.

Artifact: `mastering/voice_clone_audit.json` · Gates: [`gap_vo_gates.py`](../../src/interview_mux/gap_vo_gates.py) · Code: [`mastering_voice_clone.py`](../../src/interview_mux/mastering_voice_clone.py)

---

## Absolute bans

| Ban | Rationale |
|-----|-----------|
| **No inventing unspoken interview dialogue** | Clone may speak *new framing lines*; must not fabricate that someone said interview evidence they did not |
| **No cross-run voice reuse without re-consent** | Consent is per-run, per-speaker |
| **No clone of an unidentified / off-tape speaker** | Cannot consent on behalf of an unknown person |

Guest / content-speaker cloning is **allowed when consented** for that speaker. Prefer pickup editorially.

---

## Authorization chain

A clone is authorized when **all** hold:

1. **On-tape speaker** — `speaker_id` exists in the recording (prefer `pickup_eligible_speaker_id`)
2. **Reference approved** — `understanding/voice_reference/{speaker_id}.json` has `approved: true`
3. **Consent recorded** — explicit operator consent with actor and UTC timestamp for that speaker
4. **Scope permits the use** — the requested use is in the granted scope list

Missing any one → fail (authoritative) or advisory degrade (advisory mode).

---

## Consent record

Stored in `run_meta.json` and mirrored into the audit artifact. Includes `preferred_pickup_speaker_id` and `is_preferred_pickup` for editorial audit.

Scopes: `cold_open` | `bridges` | `outro`

Config: `mastering.quality_hardening.voice_clone.mode` (`off`|`advisory`|`authoritative`) — never relaxes off-tape / fabrication bans.
