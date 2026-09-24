"""Mode parity: identify_hosted_vo_floor must not branch on forensics or driver mode."""

from __future__ import annotations

import json
import os

import pytest

from interview_mux.hosted_vo_authority import identify_hosted_vo_floor
from run_fixtures import init_run_meta_for_test, isolated_run_ctx

_MODES = (
    ("partial", {"partial_auto": True}),
    ("full_auto", {"full_auto": True}),
    ("forensics_0", {}),
    ("forensics_1", {}),
)


def _write(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _fixture_ctx(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_hvo_mode_parity")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority._floor_waived",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority._floor_warranted",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority.need",
        lambda _ctx: 3,
    )
    _write(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_1",
                    "text": "Host asks a substantive follow-up about the guest.",
                    "delivery": "synthesize",
                }
            ]
        },
    )
    return ctx


@pytest.mark.parametrize("label,meta_patch", _MODES)
def test_identify_hosted_vo_floor_mode_parity(
    tmp_path, monkeypatch, label: str, meta_patch: dict
) -> None:
    ctx = _fixture_ctx(tmp_path, monkeypatch)
    if label == "forensics_1":
        monkeypatch.setenv("MUX_FORENSICS", "1")
    else:
        monkeypatch.setenv("MUX_FORENSICS", "0")

    def _patch_meta(meta: dict) -> None:
        meta.update(meta_patch)
        if label.startswith("forensics"):
            meta["forensics_run"] = label == "forensics_1"

    ctx.mutate_run_meta(_patch_meta)

    ident = identify_hosted_vo_floor(ctx, persist=False)
    assert ident.status == "PARTIAL"
    assert ident.need == 3
    assert ident.have == 1


def test_identify_hollow_zero_same_across_modes(tmp_path, monkeypatch) -> None:
    baseline: list[tuple[str, str, int, int]] = []
    for idx, (label, meta_patch) in enumerate(_MODES):
        ctx = isolated_run_ctx(tmp_path, f"exec_hvo_hollow_{idx}")
        init_run_meta_for_test(ctx)
        monkeypatch.setattr(
            "interview_mux.hosted_vo_authority._floor_waived",
            lambda _ctx: False,
        )
        monkeypatch.setattr(
            "interview_mux.hosted_vo_authority._floor_warranted",
            lambda _ctx: True,
        )
        monkeypatch.setattr(
            "interview_mux.hosted_vo_authority.need",
            lambda _ctx: 3,
        )
        _write(ctx, "understanding/gap_report.json", {"interviewer_lines": []})
        if label == "forensics_1":
            monkeypatch.setenv("MUX_FORENSICS", "1")
        else:
            monkeypatch.setenv("MUX_FORENSICS", "0")

        def _patch(meta: dict, mp=meta_patch, lbl=label) -> None:
            meta.update(mp)
            if lbl.startswith("forensics"):
                meta["forensics_run"] = lbl == "forensics_1"

        ctx.mutate_run_meta(_patch)
        ident = identify_hosted_vo_floor(ctx, persist=False)
        baseline.append((ident.status, ident.prose, ident.need, ident.have))

    first = baseline[0]
    assert all(row == first for row in baseline[1:]), baseline
