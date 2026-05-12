from __future__ import annotations

import json
import re
from typing import Any


_FM_BLOCK = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n", re.DOTALL)


def split_front_matter(raw: str) -> tuple[dict[str, Any], str]:
    """Parse a minimal YAML subset used in repo docs (no PyYAML dependency)."""
    if not raw.startswith("---"):
        return {}, raw
    m = _FM_BLOCK.match(raw)
    if not m:
        return {}, raw
    fm_text, body = m.group(1), raw[m.end() :]
    meta: dict[str, Any] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        key = key.strip()
        value = rest.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                meta[key] = []
            else:
                meta[key] = [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
        elif (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            meta[key] = value[1:-1]
        else:
            meta[key] = value
    return meta, body


def front_matter_json(meta: dict[str, Any]) -> str:
    return json.dumps(meta, sort_keys=True, ensure_ascii=False)
