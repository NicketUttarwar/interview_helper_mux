"""Parse agent commands from markdown files."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("cursor_execute")

COMMAND_HEADER_RE = re.compile(
    r"^## Command (\d+)\s+[—–-]\s+(.+)$",
    re.MULTILINE,
)
LEGACY_GC_HEADER_RE = re.compile(
    r"^## (GC-[A-Z0-9]+)\s+[—–-]\s+(.+)$",
    re.MULTILINE,
)
COMMAND_ID_IN_TITLE_RE = re.compile(r"\b(GC-[A-Z0-9]+)\b")
TEXT_FENCE_RE = re.compile(r"^```text\s*$", re.MULTILINE)


@dataclass(frozen=True)
class CommandSpec:
    index: int
    command_id: str
    title: str
    prompt_text: str
    source_line: int
    header_kind: str  # "command" | "legacy_gc"


def _extract_command_id(title: str, fallback: str) -> str:
    m = COMMAND_ID_IN_TITLE_RE.search(title)
    if m:
        return m.group(1)
    return fallback


def _find_text_fence(content: str, start: int) -> str | None:
    """Return prompt text from first ```text block after start, or None."""
    fence = TEXT_FENCE_RE.search(content, start)
    if not fence:
        return None
    body_start = fence.end()
    if content[body_start : body_start + 1] == "\n":
        body_start += 1
    end = content.find("\n```", body_start)
    if end < 0:
        return None
    return content[body_start:end].strip()


def _is_done_section(header_line: str, content: str, header_pos: int) -> bool:
    if "(**done**)" in header_line or "**done**" in header_line.lower():
        return True
    # Check next ~500 chars for [x] status
    snippet = content[header_pos : header_pos + 800]
    if re.search(r"\*\*Status:\*\*\s*\[x\]", snippet, re.IGNORECASE):
        return True
    if re.search(r"·\s*\*\*Status:\*\*\s*\[x\]", snippet):
        return True
    return False


def parse_commands(
    markdown_path: Path,
    *,
    include_legacy_gc: bool = False,
    skip_done: bool = False,
) -> list[CommandSpec]:
    content = markdown_path.read_text(encoding="utf-8")
    specs: list[CommandSpec] = []

    headers: list[tuple[int, int, str, str, str]] = []
    for m in COMMAND_HEADER_RE.finditer(content):
        headers.append((m.start(), int(m.group(1)), m.group(2).strip(), "command", m.group(0)))
    if include_legacy_gc:
        for m in LEGACY_GC_HEADER_RE.finditer(content):
            # Avoid duplicating if same line somehow matches both
            pos = m.start()
            if any(h[0] == pos for h in headers):
                continue
            headers.append((pos, 0, m.group(2).strip(), "legacy_gc", m.group(0)))

    headers.sort(key=lambda h: h[0])

    for i, (pos, num, title, kind, header_line) in enumerate(headers):
        if skip_done and _is_done_section(header_line, content, pos):
            logger.warning("Skipping done command at line %s: %s", content[:pos].count("\n") + 1, title[:60])
            continue

        next_pos = headers[i + 1][0] if i + 1 < len(headers) else len(content)
        section = content[pos:next_pos]
        prompt = _find_text_fence(section, 0)
        source_line = content[:pos].count("\n") + 1

        if prompt is None:
            logger.warning(
                "Skipping section without ```text prompt at line %s: %s",
                source_line,
                title[:80],
            )
            continue

        if kind == "legacy_gc":
            legacy_id = LEGACY_GC_HEADER_RE.search(header_line)
            cmd_id = legacy_id.group(1) if legacy_id else f"GC-{num}"
            idx = num if num else len(specs) + 1
        else:
            cmd_id = _extract_command_id(title, f"CMD-{num}")
            idx = num

        specs.append(
            CommandSpec(
                index=idx,
                command_id=cmd_id,
                title=title,
                prompt_text=prompt,
                source_line=source_line,
                header_kind=kind,
            )
        )

    # Stable order by document position (index field may repeat for legacy)
    return specs


def filter_command_range(
    commands: list[CommandSpec],
    from_index: int | None,
    to_index: int | None,
) -> list[CommandSpec]:
    out = commands
    if from_index is not None:
        out = [c for c in out if c.index >= from_index]
    if to_index is not None:
        out = [c for c in out if c.index <= to_index]
    return out
