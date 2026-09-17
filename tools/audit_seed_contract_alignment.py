#!/usr/bin/env python3
"""Audit seed-order vs stage-contract hard inputs (0.2.0 leapfrog ratchet).

Fails when a consecutive seed-order producer→consumer soft-underdeclares the
producer primary, when mid-pipeline stages have empty hard inputs, or when
air-order-critical correctness softs remain soft-only.

Allowlisted pairs are documented exceptions (optional/skippable producers or
seed-order carve-outs). Soft-underdeclare of topology→content_context is never
allowlisted.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.artifact_ownership import primary_path_for_stage  # noqa: E402
from interview_mux.stage_contract import load_contract  # noqa: E402
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER  # noqa: E402

# Consecutive pairs that must NOT force producer-primary hard (optional /
# skippable / seed carve-out). Keyed as (producer, consumer).
CONSECUTIVE_SOFT_ALLOWLIST: dict[tuple[str, str], str] = {
    ("audio_preclean", "ingest"): (
        "preclean is an optional checkpoint; ingest may use raw input audio when "
        "preclean is skipped or marked done without isolated.wav"
    ),
    ("ideal_cuts_propose", "ideal_cuts_materialize"): (
        "ideal_cuts.json is required only when analysis.ideal_cuts.enable — use when="
    ),
    ("mmaudio_sfx", "mix"): (
        "MusicGen/sfx can be deferred until Phase A seal; mix must not hard-block on qa"
    ),
    ("mix", "junction_snip_qa"): (
        "junction_recut_precedes_mix allows junction before first assembly; "
        "assembly.wav must stay soft/when-gated"
    ),
}

# Mid-pipeline stages allowed to keep hard:[] (first-in-phase / gate-owned / optional).
EMPTY_HARD_ALLOWLIST: dict[str, str] = {
    "framing_posture_decide": "posture gate; outputs decision from speakers+topology soft reads",
    "ideal_cuts_materialize": "gated by analysis.ideal_cuts.enable",
}

# Soft+correctness rows that must be promoted to hard (air-order / assert_consumer).
# mix←edl intentionally stays soft+correctness — junction_recut_precedes_mix.
CORRECTNESS_MUST_BE_HARD: frozenset[tuple[str, str]] = frozenset(
    {
        ("junction_snip_qa", "master/selection.json"),
        ("master_finalize", "master/edl.json"),
        ("edl", "master/transitions.json"),
    }
)

# Never allowlist — the D14 thrash class.
FORBIDDEN_SOFT_UNDERDECLARE: frozenset[tuple[str, str]] = frozenset(
    {
        ("source_topology_build", "content_context"),
        ("content_context", "talking_points_compose"),
        ("talking_points_compose", "ideal_cuts_propose"),
    }
)


@dataclass(frozen=True)
class Finding:
    kind: str
    producer: str
    consumer: str
    path: str
    detail: str


def seed_order() -> list[str]:
    return list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)


def _hard_paths(contract) -> set[str]:
    return {d.path for d in contract.inputs if d.hard and d.path}


def _soft_paths(contract) -> set[str]:
    return {d.path for d in contract.inputs if (not d.hard) and d.path}


def audit() -> list[Finding]:
    findings: list[Finding] = []
    order = seed_order()
    for i, consumer in enumerate(order):
        if i == 0:
            continue
        producer = order[i - 1]
        primary = primary_path_for_stage(producer)
        contract = load_contract(consumer)
        if contract is None:
            findings.append(
                Finding(
                    "missing_contract",
                    producer,
                    consumer,
                    "",
                    "no stage contract YAML",
                )
            )
            continue
        hard = _hard_paths(contract)
        soft = _soft_paths(contract)
        n_hard = sum(1 for d in contract.inputs if d.hard)

        if i >= 2 and n_hard == 0 and consumer not in EMPTY_HARD_ALLOWLIST:
            findings.append(
                Finding(
                    "empty_hard_midpipe",
                    producer,
                    consumer,
                    primary or "",
                    "mid-pipeline stage declares hard:[] — deferred forever under authority",
                )
            )

        if primary and primary not in hard and primary in soft:
            key = (producer, consumer)
            if key in FORBIDDEN_SOFT_UNDERDECLARE:
                findings.append(
                    Finding(
                        "soft_underdeclare_forbidden",
                        producer,
                        consumer,
                        primary,
                        "SEED_ORDER thrash class — must be hard",
                    )
                )
            elif key in CONSECUTIVE_SOFT_ALLOWLIST:
                pass
            else:
                findings.append(
                    Finding(
                        "soft_underdeclare",
                        producer,
                        consumer,
                        primary,
                        "producer primary is soft on consumer; promote to SEED_ORDER hard",
                    )
                )

        for dep in contract.inputs:
            if dep.hard or not dep.correctness or not dep.path:
                continue
            ck = (consumer, dep.path)
            if ck in CORRECTNESS_MUST_BE_HARD:
                findings.append(
                    Finding(
                        "correctness_soft",
                        dep.producer or "",
                        consumer,
                        dep.path,
                        "air-order correctness soft must be hard under authority",
                    )
                )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON")
    args = parser.parse_args(argv)
    findings = audit()
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        if not findings:
            print("OK: seed↔contract alignment clean")
        else:
            print(f"FAIL: {len(findings)} seed↔contract alignment finding(s)")
            for f in findings:
                print(f"  [{f.kind}] {f.producer} → {f.consumer} path={f.path}: {f.detail}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
