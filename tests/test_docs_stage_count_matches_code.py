"""The documented pipeline size must match the code.

README.md claimed 67 stages (34 analysis + 33 delivery) while the pipeline had
been 72 (35 + 37) for some time, and AGENTS.md had the right number. A stale
count is a small thing on its own, but it is the first number anyone reads when
deciding how far a run got, and it made "32 of 67" look closer to done than
"32 of 72" actually is.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("doc", ["README.md", "AGENTS.md"])
def test_documented_stage_counts_match_code(doc: str) -> None:
    analysis, delivery = len(ANALYSIS_ORDER), len(DELIVERY_ORDER)
    total = analysis + delivery
    text = (REPO / doc).read_text(encoding="utf-8")

    claims = [int(n) for n in re.findall(r"\*\*(\d+) stages\*\*", text)]
    assert claims, f"{doc} states no stage count to check"
    assert all(c == total for c in claims), (
        f"{doc} claims {claims} stages, code has {total}"
    )

    split = re.search(r"\((\d+) analysis \+ (\d+) delivery\)", text)
    if not split:
        split = re.search(r"(\d+) analysis \+ (\d+) delivery", text)
    assert split, f"{doc} states no analysis/delivery split to check"
    assert (int(split.group(1)), int(split.group(2))) == (analysis, delivery), (
        f"{doc} splits {split.group(1)}+{split.group(2)}, "
        f"code has {analysis}+{delivery}"
    )
