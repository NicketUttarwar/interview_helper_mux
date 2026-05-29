from pathlib import Path

from cursor_execute.expand_attachments import expand_attachments

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_expand_inlines_file():
    prompt = "Read:\n@CURSOR_EXECUTE/README.md\n\nDeliver: x"
    result = expand_attachments(prompt, REPO_ROOT, max_attachment_chars=10_000)
    assert "--- ATTACHED FILES ---" in result.prompt
    assert "--- FILE: CURSOR_EXECUTE/README.md ---" in result.prompt


def test_missing_file_marked():
    prompt = "Read:\n@does/not/exist.xyz\n"
    result = expand_attachments(prompt, REPO_ROOT, max_attachment_chars=1000)
    assert "file not found" in result.prompt
