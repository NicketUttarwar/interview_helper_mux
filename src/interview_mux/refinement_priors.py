"""Optional anonymized priors biasing L0 eligible classes (default OFF).

Full-auto does not ship ``ASSETS/refinement_priors/priors.json``. Opt in via
``analysis.refinement_passes.priors.enabled`` (``true`` / ``soft`` / ``on``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.refinement_catalog import ELIGIBLE_CLASS_VOCAB, refinement_cfg


def priors_enabled() -> bool:
    raw = (refinement_cfg().get("priors") or {}).get("enabled", False)
    if raw is True or str(raw).lower() in ("1", "true", "soft", "on", "highest"):
        return True
    return False


def _priors_path() -> Path:
    from interview_mux.config import repo_root

    cfg = merged_config()
    assets = repo_root() / cfg.get("assets_root", "ASSETS")
    return assets / "refinement_priors" / "priors.json"


def load_priors() -> dict[str, Any]:
    path = _priors_path()
    if not path.is_file():
        return {"schema_version": 1, "by_character": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 1, "by_character": {}}


def save_priors(doc: dict[str, Any]) -> None:
    path = _priors_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bias_eligible_classes(
    characters: list[str],
    eligible: list[str],
) -> tuple[list[str], bool]:
    """Return (possibly expanded eligible, prior_bias_applied). Never removes classes."""
    if not priors_enabled():
        return list(eligible), False
    priors = load_priors()
    by_c = priors.get("by_character") or {}
    out = list(eligible)
    applied = False
    for ch in characters:
        row = by_c.get(ch) if isinstance(by_c, dict) else None
        if not isinstance(row, dict):
            continue
        rates = row.get("class_accept_rates") or {}
        for cls, rate in rates.items():
            if cls not in ELIGIBLE_CLASS_VOCAB:
                continue
            try:
                r = float(rate)
            except (TypeError, ValueError):
                continue
            if r >= 0.55 and cls not in out:
                out.append(cls)
                applied = True
    return out, applied


def record_outcome(characters: list[str], class_id: str, accepted: bool) -> None:
    if not priors_enabled():
        return
    doc = load_priors()
    by_c = dict(doc.get("by_character") or {})
    for ch in characters:
        row = dict(by_c.get(ch) or {"class_accept_rates": {}, "n": 0})
        rates = dict(row.get("class_accept_rates") or {})
        prev = float(rates.get(class_id) or 0.5)
        n = int(row.get("n") or 0) + 1
        target = 1.0 if accepted else 0.0
        rates[class_id] = round((prev * (n - 1) + target) / n, 4)
        row["class_accept_rates"] = rates
        row["n"] = n
        by_c[ch] = row
    doc["by_character"] = by_c
    save_priors(doc)
