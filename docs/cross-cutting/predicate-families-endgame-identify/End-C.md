# End-C identify (sidecar)

- **Family:** Glue before EDL
- **Status suggestion:** open
- **Plain-language failure:** Reorder joins can be marked “bridged” (or EDL can resume) before a durable glue path is seated. `deferred_transition_pairs` with **spoken text only** (no WAV / omit / hitch decision) count as complete in `bridge_completeness`; full-auto bridge heal can forge `complete=True` / soft-pass `from_stage=edl`; VO framing / forward-cue quality failures often surface at EDL/QC and lack a hard heal pin to `gap_framing_compose` / `nugget_layup_compose` (heal defaults toward EDL). Heal must never soft-pass EDL on incomplete bridge; framing quality repairs must pin compose/layup writers, not EDL.
- **Example predicates:**
  - `bridge_completeness` / `bridge_incomplete` / `HARD: bridge incomplete`
  - `Reorder seam missing` / ungrounded seam / `canned_air_under_layup_authority` / stub bridge text
  - `naked_seam` / `seam_mint_reorder`
  - current transition pairs / gap VO lines missing WAV (F4 cousin — WAV path closed; deferred text cousin open)
  - `edl_narrative:vo_g1` (hint surface #5 / exec_11630 forensics; often cascades from framing/layup mismatch into EDL/audit)
  - framing-before-impact QC (“Re-run edl or gap_framing_compose”); `missing_forward_cue` / spoken speaker-role label fails under G-Framing
  - Hint surfaces (exec_11630): #2 bridge incompleteness `seg_049→seg_056`; #5 VO copy / framing / forward-cue under G-Framing → EDL
- **Producer stage(s):** `transitions`, `seam_glue` / `ensure_seam_glue`, `gap_framing_compose`, `nugget_layup_compose`, `vo_synthesize` (WAV seat after mint), `edl` (consumer — must not soft-pass incomplete bridge); driver bridge-heal / recovery `seam_mint_reorder`
- **HEAD proof (file:function):**
  - `bridge_completeness.py:_bridged_pairs` — counts `deferred_transition_pairs` with text only as bridged (comment cites exec_11630 seg_049→seg_056); no WAV / seat requirement
  - `bridge_completeness.py:missing_reorder_bridges` — also exempts via destination-only `placement=before` VO (`vo_before_targets`), not necessarily pair-specific after→before; hitch-covered pairs via EDL clips
  - `bridge_completeness.py:assert_bridges_complete` — soft mode returns incomplete doc without raise; product EDL path uses soft=False, but driver heal can override
  - `tests/test_story_placement_plan.py:test_deferred_spoken_pair_covers_reorder_bridge` — **locks in** deferred-text-as-complete (policy hole encoded as fixture)
  - `tools/full_auto_driver.py` bridge-heal (~6142–6241): assert fail + `e2e_quality_waivers` forges `complete=True` / `e2e_softened`; **also** `if not doc.get("complete")` soft-completes without a waiver check; outer `except` soft-passes `from_stage=edl`
  - `heal_routing.py:classify_heal_error` — missing-WAV bridge/VO → `vo_synthesize` (F4-good); **no** matcher for `bridge_completeness` / `Reorder seam` / framing-forward-cue prose → falls through toward EDL
  - `stage_completion.py:PRODUCER_PIN_TABLE` / `incompleteness_resume_stage` — no bridge-incompleteness / framing-quality tokens; unmatched defaults toward `edl`
  - `edl_narrative_qc.py:_validate_framing_before_impact` — error text offers “Re-run **edl** or gap_framing_compose” (ambiguous consumer pin)
  - `seam_glue.py:mint_missing_transitions` / `ensure_seam_glue` — empty ungrounded fail-closed / hitch omit (F4); loud-fail stage often `edl`, so heal defaults consumer-side
  - `stages/assembly.py` EDL path — `ensure_seam_glue(..., soft=False)` (F4-good) but does not own framing-quality repairs or deferred-WAV policy
- **Likely code:** `bridge_completeness.py`, `seam_glue.py`, `heal_routing.py`, `stage_completion.py`, `tools/full_auto_driver.py` (bridge heal), `edl_narrative_qc.py`, `transition_vo.py` (deferred under pair-freeze / VO incompleteness), `gap_framing_*` / `nugget_layup_compose` writers, `recovery_controller.py` (`seam_mint_reorder` / framing_vo_unseated → edl cousin)
- **Reuse / gap vs F*/H*:**
  - **F4 (closed):** empty ungrounded fail-closed; hitch omit spoken; missing bridge/VO WAV → `vo_synthesize` not EDL — `tests/test_f4_bridge_glue.py`. **Reuse** those paths; **do not reopen**. **Gap:** deferred-as-bridged; driver soft-pass EDL; framing / forward-cue quality → wrong pin (compose/layup vs EDL)
  - **HE-2 (closed):** unsanitary VO/bind must not soft-recover EDL playbook — adjacent; bridge incompleteness / deferred text ≠ bind-unsanitary
  - **HE-3 (closed):** preview refuses unsourced spoken glue, pins `vo_synthesize` — adjacent; pre-EDL deferred text can pass completeness before preview hears WAV
  - **Not superseded** — cousins remain; End-C stays `open` (not `partial`: no End-C-scoped producer+fixture seal yet; F4 partial reuse only)
- **Policy questions (1–3, unanswered):**
  1. Is a **deferred bridge pair** a first-class air fact (counts bridged) or only a temporary heal — and who mints the durable glue (`transitions` seated WAV vs mix last-chance vs omit spoken / hitch)?
  2. Does destination-only `placement=before` VO (`vo_before_targets`) count as pair-specific glue, or must after→before be explicit?
  3. On framing / forward-cue quality fails under G-Framing, is the sole resume writer `gap_framing_compose` vs `nugget_layup_compose` (never `edl`)?
- **Fixture gap (what MUX_FORENSICS=0 test is missing):**
  - Deferred text-only pair must **not** mark `bridge_completeness.complete` (or must pin `transitions` / `vo_synthesize`) until WAV / omit / hitch decision — today `test_deferred_spoken_pair_covers_reorder_bridge` asserts the opposite
  - Framing / forward-cue quality failure must route `classify_heal_error` / resume to `nugget_layup_compose` or `gap_framing_compose`, **never** `edl`
  - Bridge heal must not resume `edl` after incomplete assert / outer exception when quality waivers are off (`MUX_FORENSICS=0` / no e2e soft)
  - F4 fixtures do **not** cover deferred-bridged policy or framing→EDL pin
- **One-line summary:** F4 sealed empty-hinge + missing-WAV→`vo_synthesize`; End-C still open — deferred text counts as bridged, driver can soft-pass EDL, framing quality lacks a compose/layup pin.
