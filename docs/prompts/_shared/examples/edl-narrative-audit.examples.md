# edl-narrative-audit examples (reference)

QC pass on `flow_1_master/edl.json` before operator ships Flow 1. Validates narrative semantics against `selection.json`, `narrative_plan.json`, and `coverage_audit.json` — not sample-accurate waveform editing.

Pair with: `selection/edl-narrative-audit.system.txt` · [narrative-arc-plan.examples.md](./narrative-arc-plan.examples.md)

---

## Good — pass verdict with cited issues none

```json
{
  "status": "complete",
  "artifacts": {
    "verdict": "pass",
    "checks": [
      { "check_id": "chapter_opens_match_plan", "passed": true },
      { "check_id": "ordering_constraints_honored", "passed": true },
      { "check_id": "gap_vo_placements_present", "passed": true },
      { "check_id": "no_orphan_segment_in_edl", "passed": true }
    ],
    "warnings": [],
    "blocking_issues": []
  },
  "confidence": 0.91,
  "reasoning_summary": "EDL segment order respects narrative_plan chapters and ranking constraints."
}
```

**Why:** Explicit check list; `verdict: pass` only when blocking checks clear.

---

## Good — warn without fail

```json
{
  "verdict": "warn",
  "warnings": [
    {
      "check_id": "transition_density",
      "message": "Three consecutive segments lack transition lines; acceptable for fireside format.",
      "segment_ids": ["seg_030", "seg_031", "seg_032"]
    }
  ],
  "blocking_issues": []
}
```

**Why:** Editorial softness flagged; does not block ship when `narrative_qc.strict: false`.

---

## Good — fail with actionable blocking issue

```json
{
  "verdict": "fail",
  "blocking_issues": [
    {
      "check_id": "ordering_constraints_honored",
      "message": "seg_010 (scale-up numbers) appears before seg_003 (origin story) despite narrative_plan constraint.",
      "segment_ids": ["seg_003", "seg_010"],
      "suggested_action": "rerun edl_flow1 after full_master_ranking"
    }
  ]
}
```

**Why:** Concrete segment ids; ties to upstream artifact; suggests rerun target.

---

## Good — gap VO placement audit

- `gap_report` lists `delivery: record` for `seg_042` with `placement: before`.
- EDL contains `vo_pickup` event anchored before `seg_042` speech.
- Check `gap_vo_placements_present: passed`.

---

## Bad — pass despite constraint violation

- `narrative_plan.ordering_constraints` requires `seg_018` before `seg_025`.
- EDL orders `seg_025` first.
- Output still `verdict: pass`.

**Why:** High-severity arbiter reject; poisons operator trust in automated QC.

---

## Bad — vague blocking issue

```json
{
  "blocking_issues": [
    { "message": "Narrative feels wrong." }
  ]
}
```

**Why:** No `check_id`, no `segment_ids`, no `suggested_action` — not actionable.

---

## Bad — audits waveform not semantics

- Issue: "Clip at 12:04 has 3 dB louder breath" or "Crossfade too short."

**Why:** Level/timing QA belongs to mix listen gate ([post-generation-placement.md](../../../cross-cutting/post-generation-placement.md)), not narrative audit.

---

## Bad — invents segments not in selection

- References `seg_200` in issues but `selection.json` ordered list ends at `seg_048`.

**Why:** Cross-artifact ref invalid; rerun from `edl_flow1` after fixing ranking.

---

## Bad — ignores coverage_audit misses

- `coverage_audit.missing_coverage` lists `"EU regulatory timeline"` as uncovered.
- Audit `verdict: pass` with no mention.

**Why:** Coverage gaps must appear in `warnings` or `blocking_issues` per stage prompt.
