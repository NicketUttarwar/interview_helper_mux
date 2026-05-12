from __future__ import annotations

import re
from pathlib import Path

_loaded_root: Path | None = None
_config: dict[str, str] | None = None


def repo_root_from_here() -> Path:
    """Repository root: ``ai/python/mux_secrets/<this file>`` → ``parents[3]``."""
    return Path(__file__).resolve().parents[3]


_EXPORT_RE = re.compile(r"^\s*export\s+", re.IGNORECASE)


def _strip_quotes(raw: str) -> str:
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def parse_env_file(path: Path) -> dict[str, str]:
    """
    Parse a ``KEY=value`` file (``.env`` / ``secrets.env`` style) into a dict.

    Does not read ``os.environ`` and does not mutate process environment.
    """
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    text = path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = _EXPORT_RE.sub("", line)
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        out[key] = _strip_quotes(value)
    return out


def _merge_secrets_files(secrets_dir: Path) -> dict[str, str]:
    """
    Merge ``openai.env`` then ``secrets.env`` so ``secrets.env`` wins on duplicate keys
    (same precedence as the previous dotenv ordering).
    """
    merged = parse_env_file(secrets_dir / "openai.env")
    merged.update(parse_env_file(secrets_dir / "secrets.env"))
    return merged


def load_repo_config(repo_root: Path | None = None) -> Path:
    """
    Load key/value pairs from ``config/secrets/secrets.env`` and legacy
    ``config/secrets/openai.env`` into an in-process map.

    Callers must use :func:`get_config_value` — values are never written to
    ``os.environ``.
    """
    global _loaded_root, _config
    root = (repo_root if repo_root is not None else repo_root_from_here()).resolve()
    if _loaded_root == root and _config is not None:
        return root

    secrets_dir = root / "config" / "secrets"
    _config = _merge_secrets_files(secrets_dir)
    _loaded_root = root
    return root


def get_config_value(key: str, default: str = "") -> str:
    """Return a config value loaded by :func:`load_repo_config` (trimmed)."""
    if _config is None:
        raise RuntimeError("load_repo_config() must be called before get_config_value().")
    return (_config.get(key) or default).strip()


def get_config_values(keys: tuple[str, ...]) -> dict[str, str]:
    """Return ``{key: value or ''}`` for the given keys (after :func:`load_repo_config`)."""
    if _config is None:
        raise RuntimeError("load_repo_config() must be called before get_config_values().")
    return {k: (_config.get(k) or "").strip() for k in keys}
