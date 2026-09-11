# Timeline reopen meta-gate

Decide whether reopening EDL/mix/air_script (or remastering) will **significantly** improve final `master.wav` listener quality.

Return JSON only:

```json
{
  "allow": false,
  "expected_gain": 0.0,
  "refuse_reason": "marginal_floor_miss",
  "axes_allowed": []
}
```

Rules:
- Allow only when expected listener gain is meaningful (not cosmetic).
- Prefer refuse + proceed when uncertain (imperfect ship OK).
- Critical incomplete cuts and catastrophic floors are handled deterministically before this prompt.
