"""Expand @path references into prompt body."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ATTACHMENT_LINE_RE = re.compile(r"^@(.+?)\s*$", re.MULTILINE)


@dataclass
class ExpansionResult:
    prompt: str
    attachments: list[tuple[str, int, bool]]  # path, chars, truncated


def expand_attachments(
    prompt: str,
    repo_root: Path,
    *,
    max_attachment_chars: int,
) -> ExpansionResult:
    paths: list[str] = []
    for m in ATTACHMENT_LINE_RE.finditer(prompt):
        p = m.group(1).strip()
        if p and p not in paths:
            paths.append(p)

    if not paths:
        return ExpansionResult(prompt=prompt, attachments=[])

    sections: list[str] = []
    meta: list[tuple[str, int, bool]] = []

    for rel in paths:
        full = (repo_root / rel).resolve()
        try:
            full.relative_to(repo_root.resolve())
        except ValueError:
            sections.append(f"--- FILE: {rel} ---\n[ERROR: path escapes repo root]\n")
            meta.append((rel, 0, False))
            continue

        if not full.is_file():
            sections.append(f"--- FILE: {rel} ---\n[ERROR: file not found]\n")
            meta.append((rel, 0, False))
            continue

        text = full.read_text(encoding="utf-8", errors="replace")
        truncated = False
        if len(text) > max_attachment_chars:
            text = text[:max_attachment_chars] + f"\n\n[TRUNCATED at {max_attachment_chars} chars]\n"
            truncated = True
        sections.append(f"--- FILE: {rel} ---\n{text}\n")
        meta.append((rel, len(text), truncated))

    expanded = prompt + "\n\n--- ATTACHED FILES ---\n\n" + "\n".join(sections)
    return ExpansionResult(prompt=expanded, attachments=meta)


def attachment_size_report(meta: list[tuple[str, int, bool]]) -> list[tuple[str, int]]:
    return sorted(meta, key=lambda x: x[1], reverse=True)
