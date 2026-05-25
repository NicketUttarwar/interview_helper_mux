# Segment schema

Canonical segment object passed between LLM stages and audio editing.

## Segment

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `segment_id` | string | yes | Stable id, e.g. `seg_001` |
| `start_ms` | integer | yes | Start time in source audio |
| `end_ms` | integer | yes | End time (`end_ms` > `start_ms`) |
| `speaker_id` | string | yes | Diarization label |
| `speaker_role` | enum | yes | `interviewer`, `interviewee`, `unknown` |
| `type` | enum | yes | See types below |
| `text` | string | yes | Transcript text for range |
| `topic_tags` | string[] | no | Theme labels |
| `ready` | boolean | no | Gap analysis: safe to include without fix |
| `self_explanatory` | boolean | no | From missing-framing stage |

## Segment types

| Type | Typical speaker |
|------|-----------------|
| `interviewer_question` | interviewer |
| `interviewee_answer` | interviewee |
| `interviewer_reaction` | interviewer |
| `setup` | interviewer |
| `aside` | either |
| `coda` | either |

## Speaker

```json
{
  "id": "spk_0",
  "role": "interviewer",
  "display_name": null,
  "confidence": 0.92,
  "evidence": "short turns, question density"
}
```

## Collections

- `segments/manifest.json` — `{ "segments": [ ... ] }`
- `segments/boundaries.json` — raw boundary proposals before classification

See [json-schemas/segment.schema.json](./json-schemas/segment.schema.json).
