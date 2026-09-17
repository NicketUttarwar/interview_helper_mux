# Stage clinic dossier — {{STAGE_ID}}

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: not_started | L2_target: not_started | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `{{STAGE_ID}}`
- seed_position: {{SEED_POSITION}} ({{SEED_PHASE}})
- tier (contract claim): {{TIER}} — verify vs body
- primary_artifact_path (SSOT claim): {{PRIMARY_PATH}}
- immediate upstream producers (from code — fill in L1):
- immediate downstream consumers (code + contract claim):
- gate_adjacency: none | G0 | G-Framing | G1 | preclean | G-Publish | other:
- LLM?: no | OpenAI/external (prompt ids:) | local-heavy only (skip deep dive)
- thrash_hotspot: yes | no
- test_gravity: none | thin | solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [ ] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [ ] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [ ] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [ ] §5.4 Gates / GUI / partial
- [ ] §5.5 Config flags + defaults
- [ ] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/{{STAGE_ID}}.yaml`
- Map: `.cursor/stage-clinic/maps/{{STAGE_ID}}.possibility.md`
- Target: `.cursor/stage-clinic/targets/{{STAGE_ID}}.target.md`
- Notes: `.cursor/stage-clinic/notes/{{STAGE_ID}}.decisions.md`
- Module (fill in L1):
- Tests (fill in L1):

## Pack completeness

discovery_status: not_started  
Do not mark L1 complete without §5.8 gate (plan §5.8).
