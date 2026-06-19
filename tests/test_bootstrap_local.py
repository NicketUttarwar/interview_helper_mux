from __future__ import annotations

from pathlib import Path

from interview_mux.local_runtime import write_install_manifest


def test_write_install_manifest_fields(tmp_path):
    repo = tmp_path / "DeepFilterNet"
    repo.mkdir()
    venv = tmp_path / "venv"
    venv.mkdir()
    dest = write_install_manifest(
        tmp_path,
        runtime_id="deepfilter",
        repo_url="https://github.com/rikorose/deepfilternet.git",
        repo_dir=repo,
        venv_dir=venv,
        verified=True,
    )
    assert dest.is_file()
    import json

    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["runtime_id"] == "deepfilter"
    assert data["verified"] is True
    assert data["venv_dir"] == str(venv)


def test_clone_script_paths_exist():
    root = Path(__file__).resolve().parents[1]
    clone = root / "scripts" / "clone_local_audio_repos.sh"
    bootstrap = root / "scripts" / "lib" / "bootstrap_local_runtimes.sh"
    verify = root / "scripts" / "verify_local_models.sh"
    assert clone.is_file()
    assert bootstrap.is_file()
    assert verify.is_file()
    text = clone.read_text(encoding="utf-8")
    assert "ASSETS/local_mmaudio/MMAudio" in text
    assert "ASSETS/local_deepfilter/DeepFilterNet" in text
