# Nugget Layup System

Canon for recovering discarded native information as **pre-native synthetic VO**.

When selection drops segments, the facts still live in the full transcript. This system:

1. **`nugget_corpus_mine`** (flagship) — mines atomic grounded nuggets from **all** speakers / segments (kept + excluded), plus talking points / ideal cuts.
2. **`nugget_layup_compose`** (flagship) — for each ordered native, writes a host lay-up that weaves relevant unused nuggets and unlocks the upcoming clip.
3. **Publish** — lay-ups become authoritative `gap_report.interviewer_lines` with `placement: before` (episode orientation preserved).
4. **Realize** — existing G1 synthesis + EDL `_gap_lines_for_segment(..., "before")` unchanged.

Ideal: nearly every kept native has a contentful before-VO so high-value excluded tape still reaches the listener.

## Authority vs legacy VO planners

| Legacy | Role under layup authority |
|--------|----------------------------|
| `gap_framing_compose` | Gap *detection* hints only; not authoritative air copy |
| `gap_framing_recompose` | Thin adapter: re-publish layups / keep orientation (`nugget_layup_authority`) |
| `synthetic_framing_plan` | Demoted to empty lines (no content recovery LLM) |
| `seam_glue` placeholders | Suppressed when a before-VO layup already targets the next native |

## Artifacts

- `understanding/nugget_corpus.json`
- `understanding/nugget_layup_plan.json`
- `understanding/nugget_layup_qc.json`
- `understanding/gap_report.json` (layup lines + orientation)

## Config

See `analysis.nugget_layup.*` in [config-keys.md](./config-keys.md).

## Prompts

- [`docs/prompts/nugget_layup/nugget-corpus-mine.system.txt`](../prompts/nugget_layup/nugget-corpus-mine.system.txt)
- [`docs/prompts/nugget_layup/nugget-layup-compose.system.txt`](../prompts/nugget_layup/nugget-layup-compose.system.txt)

## Constraints

- Grounded paraphrase only — no invented dialogue ([NORTH_STAR](../../NORTH_STAR.md)).
- No “welcome back” / chapter meta speech.
- Must not restate the upcoming native’s opening; forward-cue required.
- Exactly one early episode orientation remains selection-independent.
