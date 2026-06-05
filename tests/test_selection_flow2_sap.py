from __future__ import annotations

from interview_mux.context_volley import _shape_stage_input
from interview_mux.run_context import RunContext
from interview_mux.stages import selection_flow2
from run_fixtures import minimal_content_brief, minimal_flow2_selection, minimal_source_acoustic_profile


def test_sfx_brief_build_input_wires_source_acoustic_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_303", create=True)
    ctx.write_json("flow_2_highlights/selection.json", minimal_flow2_selection(highlights=[]))
    ctx.write_json("understanding/content_brief.json", minimal_content_brief(thesis="Test"))
    ctx.write_json(
        "understanding/source_acoustic_profile.json",
        minimal_source_acoustic_profile(
            pacing={
                "pace_class": "conversational",
                "global_wpm": 142,
                "wpm_by_quartile": [130, 140, 145, 150],
                "pause_p50_ms": 680,
            },
            mix_contract={"underscore_policy": "sparse", "duck_under_speech_db": 18},
            placement_hints={"stinger_density": "low"},
        ),
    )

    def fake_run_flow_llm_stage(_ctx, _stage_key, _prompt_rel, build_input, persist):
        payload = build_input(_ctx)
        assert payload["source_acoustic_profile"]["pace_class"] == "conversational"
        assert payload["pace_class"] == "conversational"
        assert payload["underscore_policy"] == "sparse"
        persist(_ctx, {"transitions": []})
        return {"status": "complete"}

    monkeypatch.setattr(selection_flow2, "run_flow_llm_stage", fake_run_flow_llm_stage)
    selection_flow2.run_sfx_brief(ctx)
    assert ctx.is_done("sfx_brief")


def test_sfx_brief_volley_includes_source_acoustic_profile():
    raw = {
        "selection": {"highlights": []},
        "content_brief": {"thesis": "Test"},
        "source_acoustic_profile": {
            "pace_class": "conversational",
            "global_wpm": 142,
            "mix_contract": {"underscore_policy": "sparse", "duck_under_speech_db": 18},
            "placement_hints": {"stinger_density": "low"},
        },
        "pace_class": "conversational",
        "underscore_policy": "sparse",
    }
    shaped = _shape_stage_input("sfx_brief", raw)
    sap = shaped["source_acoustic_profile"]
    assert sap["pace_class"] == "conversational"
    assert sap["mix_contract"]["underscore_policy"] == "sparse"
    assert sap["placement_hints"]["stinger_density"] == "low"
