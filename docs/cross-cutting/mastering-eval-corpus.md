# Mastering eval corpus

Fixture taxonomy that makes "the mastering got better" a measurable claim. Canon: [mastering-quality-hardening.md](./mastering-quality-hardening.md).

**Problem:** without diverse fixtures, quality is anecdotal — a change that helps a technical 1:1 can quietly ruin a noisy panel.

Location: `tests/fixtures/mastering_quality/`

---

## Taxonomy axes

Every fixture is tagged along seven axes so coverage gaps are visible:

| Axis | Values |
|------|--------|
| `topology` | `monologue`, `balanced_1on1`, `guest_heavy`, `panel`, `sparse_host` |
| `acoustics` | `clean`, `noisy` |
| `duration` | `short` (<20 min), `long` (>60 min) |
| `theme` | `technical`, `emotional`, `historical`, `comedy`, `business` |
| `vo_reference` | `none`, `excellent` |
| `sfx_assets` | `sparse`, `rich` |
| `integrity_risk` | `clean`, `landmined` |

A fixture is a small JSON bundle, not audio: segment manifest excerpt, speaker roles, transcript snippets, asset catalog stubs, and topology. Audio-dependent assertions live in the optional smoke tier.

---

## Fixture contents

```
tests/fixtures/mastering_quality/{fixture_id}/
  fixture.json        # tags + inputs (segments, speakers, assets, topology)
  expectations.json   # routing hints, diversity floor, expected integrity findings
```

`expectations.json` declares what the hardening layer should conclude:

| Key | Meaning |
|-----|---------|
| `routing_hints` | Fields expected `required` / `skip` for this source |
| `diversity_floor` | Minimum pairwise diversity the candidates must reach |
| `expected_findings[]` | Integrity landmines that must be caught (`class_id` + `segment_id`) |
| `must_not_flag[]` | False-positive traps that must stay clean |
| `feasibility` | Expected verdict per seeded candidate |

---

## Seeded landmines

The `landmined` fixtures deliberately contain the traps semantic integrity must catch:

| Fixture trait | Landmine |
|---------------|----------|
| Negated hook | `"I would never say the market is safe"` clipped to `"the market is safe"` |
| Causal inversion | Effect segment ordered before its `because` clause |
| Orphaned referent | Segment opening `"that number"` with the antecedent excluded |
| False reaction | Laugh reaction moved next to an unrelated statement |
| VO overstatement | VO framing asserts a claim the guest hedged |

Each is paired with a near-miss in a `clean` fixture so the detector is measured on precision as well as recall.

---

## Metrics

| Metric | Target |
|--------|--------|
| Integrity recall on seeded landmines | 1.0 for `critical` classes |
| Integrity false-positive rate on `must_not_flag` | 0 |
| Feasibility verdict accuracy | 1.0 (deterministic) |
| Diversity floor met after enforcement | 1.0 |
| Routing agreement with hints | ≥ 0.8 per fixture |

Deterministic compilers are asserted exactly. LLM-dependent behavior is asserted only through schema contract tests — no flaky score assertions in CI.

---

## Test tiers

| Tier | Files | Network |
|------|-------|---------|
| Deterministic | `tests/test_mastering_quality_compilers.py` | none |
| Policy | `tests/test_mastering_quality_voice.py` | none |
| Contract | `tests/test_mastering_quality_critics_contract.py` | none (fixture responses) |
| Smoke | `tests/test_mastering_quality_audition_smoke.py` | none (manifest only, no render) |

CI runs all four. Real audio renders and real LLM calls stay out of the default suite.

---

## Adding a fixture

1. Create the directory with `fixture.json` + `expectations.json`
2. Tag all seven axes
3. Add landmines to `expected_findings` and near-misses to `must_not_flag`
4. The taxonomy coverage test fails if any axis value has zero fixtures — that is the signal to add one
