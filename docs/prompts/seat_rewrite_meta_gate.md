# Seat rewrite meta-gate

After VO/air seat freeze, decide whether a proposed omit/reseat rewrite is **high opportunity** for the listener.

Return JSON only:

```json
{
  "allow": false,
  "opportunity_score": 0.0,
  "expected_listener_gain": 0.0,
  "rewrite_ops": [],
  "refuse_reason": "low_opportunity"
}
```

`rewrite_ops` items: `{"action":"omit"|"revive","line_id":"..."}`.

Prefer refuse when the change is thrashy or low value. Catastrophe (G1 red, missing seated WAV, operator) is handled outside this prompt.
