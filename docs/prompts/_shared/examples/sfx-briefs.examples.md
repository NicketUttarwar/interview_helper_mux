# SFX briefs examples (reference) — Flow 1 podcast + Flow 2 montage

## Podcast (`podcast_sfx_brief`)

**Good — ducked bed**

- `beds` entry with `level_db: -26` and narrative that supports ducking under speech for a dense explanation block.

**Good — varied stingers**

- Chapter stingers share mood but different plain-language `description` per chapter (not copy-paste).

**Bad — speech-hostile**

- Loud whoosh bed under dense interviewee monologue without ducking note — violates intelligibility-first rules.

## Montage (`sfx_brief` / Flow 2)

**Good — cold open**

- `cold_open.description` sets tone in ≤2.5s metaphor; `mood` matches clip 1.

**Good — transition pair**

- `from_clip_rank: 1`, `to_clip_rank: 2`, distinct `description` from cold open.

**Bad — identical descriptions**

- Same `description` string for every `transitions[]` row — violates “do not use the same description for every transition”.
