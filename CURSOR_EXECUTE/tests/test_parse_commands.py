from pathlib import Path

from cursor_execute.parse_commands import filter_command_range, parse_commands

FIXTURE = Path(__file__).parent / "fixtures" / "sample_commands.md"


def test_parse_command_n_headers():
    cmds = parse_commands(FIXTURE)
    assert len(cmds) == 2
    assert cmds[0].command_id == "GC-TEST1"
    assert cmds[1].command_id == "GC-TEST2"
    assert "README.md" in cmds[0].prompt_text or "@README.md" in cmds[0].prompt_text


def test_skip_done():
    cmds = parse_commands(FIXTURE, skip_done=True)
    assert len(cmds) == 1
    assert cmds[0].command_id == "GC-TEST1"


def test_include_legacy_gc():
    cmds = parse_commands(FIXTURE, include_legacy_gc=True)
    ids = [c.command_id for c in cmds]
    assert "GC-LEGACY" in ids or any("LEGACY" in c.title for c in cmds)


def test_filter_range():
    cmds = parse_commands(FIXTURE)
    sliced = filter_command_range(cmds, 2, 2)
    assert len(sliced) == 1
    assert sliced[0].index == 2
