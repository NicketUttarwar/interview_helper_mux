# Cluster & dig failures — exec_13183 (Mohan full-auto)

**Run:** `exec_13183_d19c15b58ab4_20260924T001619Z`  
**Input:** `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3`  
**Outcome of the campaign:** shipped (`master.wav`, delight ~0.98, PMQ pass).  
**Scope of this doc:** only the **cluster** and **dig** failures from that run — the ones that share a deeper mechanism or still deserve design follow-up. Point fixes (i3 letter-start inherit, i5 EDL blank pre-repair, i6 ESR self-lease) are omitted here.

**How to read depth**

| Label | Meaning |
|-------|---------|
| **Cluster** | Same underlying mechanism as other bugs; fixing one symptom may leave siblings. |
| **Dig** | Worth a short design pass before trusting the next full-auto to be quiet. |

---

## Big picture (simple)

Three kinds of “lying” showed up again and again:

1. **Fake finished** — the pipeline stamped a stage as done (or promoted an old artifact) without actually doing the real work.
2. **Two books for host VO** — the gap/omit book said one thing; the EDL/WAV/floor book said another.
3. **Wrong next stage** — heal/driver jumped to the wrong producer and made thrash worse.

Everything below is a concrete story of one of those.

---

## Cluster A — Hollow “done” / orphan promote  
*(stages look finished when the real product work never landed)*

### Shared root cause

The pipeline has helpers that say: “this stage’s output file already exists → stamp `.stage_done` / promote orphan.” That is useful when a crash left good artifacts. It is **dangerous** when:

- the stamp exists without a real plan/render, or  
- an old speech-only mix is still on disk while music remaster is owed.

Then full-auto thinks it can move on, thrash-loops, or blocks later stages forever.

---

### i1 — Orphan layup stamp without a plan

| | |
|--|--|
| **Depth** | Cluster |
| **When** | Early delivery / gap framing |
| **What you saw** | Layup / gap framing looked “Finished” and the run thrashed instead of composing a real plan. |

**What happened (simple)**  
Something left a **done stamp** (or equivalent “we already finished layup”) even though there was **no real layup plan**. The pipeline treated that as success and tried to advance. Downstream stages expected real layup work that was never done → hollow Finished thrash.

**Root cause**  
“Stamp alone” was enough to look complete. Producer should have fallen through to **compose** when the plan was missing (HG-5 style).

**How it caused a bug**  
Full-auto cannot tell “fake finished” from “really finished.” It keeps re-entering the same area, never minting the missing plan, and burns cycles / identical-failure counters.

**Outcome**  
- Cleared orphan stamp; stamp-alone must admit compose.  
- Cascade test: `test_i1_orphan_layup_stamp_cleared_admits_fallthrough` (in `tests/test_gap_framing_compose_harden.py`).  
- Predicate flipped; run continued.

**Still dig?**  
Yes, lightly — same *class* as i10 (promote/stamp without land). A shared rule (“promote only after real producer land”) would shrink this family.

---

### i10 — Music remaster blocked: fake mix “done” again

| | |
|--|--|
| **Depth** | Cluster / Dig |
| **When** | After MusicGen themes; before junction / master |
| **What you saw** | `cannot run junction_snip_qa: delivery epoch speech_first_remaster_pending` while mix already looked done. |

**What happened (simple)**  
The show was allowed to **mix speech first**, then generate music beds, then **remaster mix with music**. When music finished, the system correctly unmarked mix and set `remaster_owner=music_epoch`.

Then **orphan promote** looked at the **old** speech-only `assembly.wav`, decided mix was “complete,” and restamped `.stage_done/mix` **without** clearing the remaster flag and **without** rewriting assembly with beds.

Junction correctly refused: remaster still owed. Driver kept retrying junction → stuck.

**Root cause**  
Orphan promote / incompleteness treated a **pre-beds** seated assembly as a finished music remaster. `clear_remaster` only runs on a real mix land path — promote skipped that path.

**How it caused a bug**  
Two truths at once: “mix is done” (marker) and “beds remaster still owed” (epoch). Junction cannot run; mix will not re-run; ship stalls.

**Outcome**  
- Added `music_epoch_pre_beds_seat`: if remaster is in flight and assembly is older than the remaster stamp, mix is **incomplete**.  
- `ensure_speech_first_remaster` demotes hollow mix.  
- Cascade: `tests/test_i10_orphan_promote_blocks_music_epoch_remaster.py`.  
- Forced real remaster mix (~450 MB assembly with beds) → cleared remaster → junction → master → **ship**.

**Still dig?**  
Yes — generalize “orphan promote must not satisfy in-flight remaster / unpaid land” beyond mix.

---

## Cluster C — Hosted VO floor / orientation dual-SSOT  
*(gap book vs seat/WAV/floor book disagree)*

### Shared root cause

Host voice-over is governed by **more than one source of truth**:

- gap report / omit / `native_open_self_orients` (“we don’t need that line”),  
- aspirational / hosted floor (“we still need N synth seats”),  
- EDL / disk WAV (“the line is already seated or recorded”).

When those disagree, full-auto either **skips work it still needs**, **keeps escalating forever**, or **fails preflight** because the script and the timeline don’t match.

---

### i4 — Aspirational continue at zero seats + wrong resume pin

| | |
|--|--|
| **Depth** | Dig |
| **When** | Hosted framing / layup / VO path |
| **What you saw** | Pipeline tried to “aspirational continue” with **zero** synthetic VO seats; Gap VO “no synthesize” heal jumped to **edl_narrative_audit** and thrashed. |

**What happened (simple)**  
Hosted mode says “we’ll put host VO in.” Aspirational logic said “OK to proceed for now” even when **no** synth lines were actually seated. Separately, a “no synthesize lines” failure was pinned to the **wrong** stage (narrative audit) instead of **layup compose**, so heal never minted the missing VO.

Orientation could also be dropped while the hosted path was still hollow.

**Root cause**  
Aspirational proceed was allowed at **have=0**. Resume pin for Gap VO miss pointed at a **consumer**, not the **producer**. Orientation keep rules didn’t force-hold when hosted floor was empty.

**How it caused a bug**  
The run walked past the only stage that can create seats, then failed or looped on later stages that assume seats exist.

**Outcome**  
- Refuse aspirational at zero seats.  
- Force-keep orientation when hosted is hollow.  
- Pin resume → `nugget_layup_compose`.  
- Cascade: `tests/test_i4_hollow_hosted_vo_zero.py`.  
- Continued from layup.

**Still dig?**  
**Yes — highest priority dig.** This is the center of the VO dual-SSOT mess; i7 and i8 are siblings.

---

### i7 — Stale “floor unsatisfiable” blocked synth after seats existed

| | |
|--|--|
| **Depth** | Cluster (symptom of i4 world) |
| **When** | After some VO seats were reminted; still blocked entering `vo_synthesize` |
| **What you saw** | Escalation `hosted_vo_floor_unsatisfiable` stayed open even after active synth seats ≥ 1. |

**What happened (simple)**  
Earlier, the floor said “impossible / unsatisfiable” and stamped an escalation. Later, seats **were** reminted, but the **old escalation sticker** still blocked stability / Chatterbox.

**Root cause**  
Escalation was sticky; clearer did not clear when reality improved (active seats ≥ 1).

**How it caused a bug**  
Synthesize could not run even though the floor was no longer empty → VO path stalled again.

**Outcome**  
- Clear layup floor escalation when active synth seats ≥ 1.  
- Cascade: `tests/test_i7_stale_layup_floor_escalation.py`.  
- Orientation WAV minted; continued.

**Still dig?**  
Only as part of the i4 orientation/floor SSOT dig — not a separate product redesign.

---

### i8 — Orientation omitted in gap but still required on EDL/WAV

| | |
|--|--|
| **Depth** | Cluster / Dig |
| **When** | `assembly_preview` preflight |
| **What you saw** | `missing_current_script` for `vo_preface_episode_orientation` — gap had omitted it under `native_open_self_orients`, but EDL/WAV still expected/seated it. |

**What happened (simple)**  
One rule said: “native open already orients itself → omit host orientation line from the gap.”  
Another path had already **seated or written** that orientation on disk / EDL.  
Preview preflight: “script for this seated VO is missing” → fail.

**Root cause**  
Omit policy and seat/WAV reality were not reconciled. `ensure_episode_orientation` needed to **force-keep/remint** when WAV or EDL seat already exists.

**How it caused a bug**  
Assembly preview cannot build a consistent heard timeline; delivery stops until orientation is reminted into the gap/script.

**Outcome**  
- Force-keep/remint when orientation WAV or EDL `vo_pickup` seat exists.  
- Cascade: `tests/test_i8_keep_orientation_when_edl_seated.py`.  
- Gap reminted live; preflight OK.

**Still dig?**  
**Yes** — same dual-SSOT as i4: one authority for “keep / omit / seat orientation.”

---

## Cluster D (related) — EDL seating after orientation

### i9 — Layup WAVs on disk but not in EDL (phantom VO) + missing ledger

| | |
|--|--|
| **Depth** | Cluster (ties to C) |
| **When** | Pre-mix / EDL rebuild after orientation work |
| **What you saw** | `vo_audibility_drift` / **phantom_vo**: layup WAVs existed on disk but were not in the EDL. Heal rebuild also hit **edl_unsanitary** (missing `assembly_ledger`). |

**What happened (simple)**  
After seating opening orientation VO, EDL build applied a rule that effectively **wiped** the following “before” layup/required lines from the timeline. Audio files for those layups were still on disk → checkers reported phantoms (WAV without EDL seat). Separately, sanitary expected an `assembly_ledger` that was missing, which blocked heal rebuild.

**Root cause**  
Post-orientation EDL stacking rule was too aggressive for layup/required before-lines. Ledger auto-write was missing on the sanitary path.

**How it caused a bug**  
Mix/audibility gates refuse a timeline that doesn’t match disk VO; heal can’t rebuild while unsanitary → stuck before mix.

**Outcome**  
- After opening VO, still seat `nugget_layup` / required before-lines.  
- Auto-write missing `assembly_ledger` during edl sanitary.  
- Cascade: `tests/test_i9_layup_seats_after_opening_vo.py`.  
- Live EDL seated orientation + layups; phantoms cleared; continued to music/mix.

**Still dig?**  
Light — fold “what must stay seated after preface VO” into the same orientation/EDL seating table as Cluster C.

---

## How these clusters connect (one diagram in words)

```
Fake done / orphan promote (A: i1, i10)
        │
        │  “We’re finished” when we’re not
        ▼
   Wrong stage / thrash
        │
Host VO two books (C: i4 → i7 → i8)
        │
        │  omit vs floor vs WAV/EDL
        ▼
EDL seating survivors (D: i9)
        │
        ▼
   Mix / remaster / junction / ship
```

i10 was late delivery but the **same hollow-done idea** as i1.  
i7/i8/i9 were **aftershocks** of the hosted VO / orientation disagreement started in i4.

---

## Dig backlog (for a quieter next full-auto)

| Priority | Dig | Why |
|----------|-----|-----|
| 1 | ~~**Orientation + hosted floor + gap omit SSOT** (i4, i7, i8, part of i9)~~ | **CLOSED** — [`hosted_vo_authority.py`](../../src/interview_mux/hosted_vo_authority.py) + [hosted-vo-authority.md](../../docs/cross-cutting/hosted-vo-authority.md): `identify_hosted_vo_floor`, disposition priority, aspirational never at HOLLOW_ZERO, escalation triple-clear, EDL survivors. |
| 2 | ~~**Orphan promote / hollow done policy** (i1, i10)~~ | **CLOSED** — Land Honesty `unpaid_land_reason` / `unpaid_land_blocks_promote` ([`done_authority.py`](../../src/interview_mux/done_authority.py)): remaster + pre-beds + speech_first + remutate + layup stamp-alone + shared-path; permanence lint; matrix [`tests/test_unpaid_land_matrix.py`](../../tests/test_unpaid_land_matrix.py); real-exec [`tests/test_i10_hollow_unpaid_real_exec.py`](../../tests/test_i10_hollow_unpaid_real_exec.py) + [`tests/fixtures/exec_13183_hollow_unpaid/`](../../tests/fixtures/exec_13183_hollow_unpaid/). |
| 3 | ~~**EDL seating after preface VO** (i9)~~ | **CLOSED** into #1 survivor table (idx==0 + later). |

---

## Non-cluster residues (post-ship hygiene)

Not dig priorities — forensics thrash on exec_13183 that still deserved explicit close-out:

| Residue | Fix | Tests / fixtures |
|---------|-----|------------------|
| `segment_starts_unavailable` + letter kids | Inherit spans + persist `_meta.inherited_segment_spans` | [`tests/fixtures/exec_13183_selection_residues/`](../../tests/fixtures/exec_13183_selection_residues/) · [`tests/test_i13183_selection_residues.py`](../../tests/test_i13183_selection_residues.py) |
| `selection_commit_refused` / `clearly_media_ip_pitch` | `normalize_media_ip_cta_rows` before selection commit | same suite |
| `authority_denied` (esp. delight under mix) | DENY → ALLOW owner pin; delight writes `stage_key=listen_delight_audit` | [`tests/test_i13183_ownership_deny.py`](../../tests/test_i13183_ownership_deny.py) |

---

## Fresh full-auto quiet checklist

Documented acceptance bar for the **next** campaign (not launched in the remainders close-out). Predicates must be absent or single-shot (no identical-failure streak):

| Must be quiet / single-shot | Maps to |
|-----------------------------|---------|
| `speech_first_remaster_pending` with mix looking done | Dig #2 / i10 |
| Layup/gap premature_complete with missing plan | Dig #2 / i1 |
| `hosted_vo_floor_unsatisfiable` sticky after seats ≥1 | C (lock) |
| `phantom_vo` / `edl_survivor_wipe` for layups after orientation | D/i9 (lock) |
| `segment_starts_unavailable` identical streak | Selection residue |
| `selection_commit_refused` on `clearly_media_ip_pitch` | Selection residue |
| `authority_denied` identical streak same path | Ownership residue |
| mix persist DENY on `listen_delight_audit.json` | Ownership residue |

---

## Campaign outcome (reminder)

Despite these cluster/dig bugs, the **same run** was patched in place and **shipped**:

- `master/master.wav` ~225 MB, `verify_master` OK  
- Listen delight overall ~0.9758  
- PMQ `publish_allowed: true`  
- Local publish package present; S3 waited on G-Publish consent (ops, not a dig)

This file is the memory of **what still wants design**, not a claim that the ship was soft.
