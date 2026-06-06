"""Tests for E2E secrets loading."""

from __future__ import annotations

from pathlib import Path

from e2e_runner.secrets import cursor_api_key, load_secrets


def test_load_secrets_ignores_comments_and_blanks(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "config" / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "secrets.env").write_text(
        "\n".join(
            [
                "# comment",
                "",
                'CURSOR_API_KEY="cursor_test_key"',
                "OPENAI_API_KEY=sk-test",
            ]
        ),
        encoding="utf-8",
    )
    loaded = load_secrets(tmp_path)
    assert loaded["CURSOR_API_KEY"] == "cursor_test_key"
    assert loaded["OPENAI_API_KEY"] == "sk-test"


def test_cursor_api_key_prefers_env(monkeypatch, tmp_path: Path) -> None:
    secrets_dir = tmp_path / "config" / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "secrets.env").write_text(
        "CURSOR_API_KEY=cursor_from_file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CURSOR_API_KEY", "cursor_from_env")
    assert cursor_api_key(tmp_path) == "cursor_from_env"


def test_cursor_api_key_reads_secrets_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    secrets_dir = tmp_path / "config" / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "secrets.env").write_text(
        "CURSOR_API_KEY=cursor_from_file\n",
        encoding="utf-8",
    )
    assert cursor_api_key(tmp_path) == "cursor_from_file"
