import subprocess
from pathlib import Path

from cursor_execute.git_stats import diff_since_snapshot, take_snapshot, validate_git_repo

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_git_snapshot_and_diff():
    validate_git_repo(REPO_ROOT)
    before = take_snapshot(REPO_ROOT)
    summary = diff_since_snapshot(
        REPO_ROOT,
        before,
        command_index=1,
        command_total=1,
        command_id="T",
        command_title="Test",
    )
    assert summary.total >= 0


def test_git_repo_required():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=path,
            check=True,
            capture_output=True,
            env={**__import__("os").environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
        )
        validate_git_repo(path)
        snap = take_snapshot(path)
        assert snap.head
