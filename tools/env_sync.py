#!/usr/bin/env python3
"""Compare this machine against the reference environment and align it.

  python3 tools/env_sync.py snapshot      # reference Mac only: write config/env-lock/
  python3 tools/env_sync.py               # check, report mismatches (exit 1 if any)
  python3 tools/env_sync.py --fix         # check, then align (asks before each action)
  python3 tools/env_sync.py --fix --yes   # align without prompting
  python3 tools/env_sync.py --fix --prune # also uninstall pip packages not in the lock

Stdlib only, so it runs before any venv exists. Needs the venvs from
./scripts/bootstrap_venv.sh for the pip/model checks.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_DIR = ROOT / "config" / "env-lock"
MANIFEST = LOCK_DIR / "manifest.json"
BREW = "/opt/homebrew/bin/brew"
PIP_TIMEOUT = 1800
FORMULAS = {"python3.12": "python@3.12", "ffmpeg": "ffmpeg", "node": "node", "rustc": "rust"}
BUILD_ONLY = {"node", "npm", "rustc"}
MODEL_TIMEOUT = 7200

VENVS = {".venv": ROOT / ".venv"} | {
    p.parent.parent.relative_to(ROOT).as_posix(): p.parent.parent
    for p in sorted((ROOT / "ASSETS").glob("local_*/venv/bin/python"))
}
HF_CACHES = [ROOT / "ASSETS" / "local_musicgen" / "hf_cache" / "hub"]

OK, WARN, BAD = "OK  ", "WARN", "DIFF"
results: list[tuple[str, str, str]] = []  # (level, what, detail)
fixes: list[tuple[str, list[str], int]] = []  # (description, argv, timeout)


def run(argv: list[str], timeout: int = 60) -> str:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def first_line(s: str) -> str:
    return s.splitlines()[0] if s else ""


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def venv_python(venv: Path) -> Path:
    return venv / "bin" / "python"


def pip_freeze(venv: Path) -> dict[str, str]:
    """name -> exact requirement line, for pinned and git-pinned packages."""
    out = run([str(venv_python(venv)), "-m", "pip", "freeze"], 120)
    pins = {}
    for line in out.splitlines():
        if "interview_mux" in line or "interview-mux" in line:
            continue  # this repo itself, installed editable at whatever commit
        if "file://" in line or line.startswith("-e /"):
            continue  # local native build (e.g. DeepFilterNet pyDF): machine path; checked by RUNTIME_IMPORTS
        m = re.match(r"^(?:-e )?(?:git\+\S+#egg=|)([A-Za-z0-9_.-]+)(?:==|\s@\s|$)", line)
        if m:
            pins[norm(m.group(1))] = line
    return pins


def tool_versions() -> dict[str, str]:
    py = shutil.which("python3.12") or BREW.replace("brew", "python3.12")
    return {
        "python3.12": first_line(run([py, "--version"])).replace("Python ", ""),
        "ffmpeg": (re.search(r"version (\S+)", first_line(run(["ffmpeg", "-version"]))) or [None, ""])[1],
        "node": run(["node", "--version"]).lstrip("v"),
        "npm": run(["npm", "--version"]),
        "rustc": (re.search(r"rustc (\S+)", run(["rustc", "--version"])) or [None, ""])[1],
    }


def hardware() -> dict[str, str]:
    return {
        "macos": run(["sw_vers", "-productVersion"]),
        "arch": platform.machine(),
        "chip": run(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "ram_gb": str(int(run(["sysctl", "-n", "hw.memsize"]) or 0) // 2**30),
    }


def hf_models() -> dict[str, str]:
    models = {}
    for hub in HF_CACHES:
        for d in sorted(hub.glob("models--*")):
            ref = d / "refs" / "main"
            if ref.exists():
                models[d.name.removeprefix("models--").replace("--", "/")] = ref.read_text().strip()
    return models


def snapshot() -> None:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"tools": tool_versions(), "hardware": hardware(), "models": hf_models(), "venvs": {}}
    for name, venv in VENVS.items():
        if not venv_python(venv).exists():
            print(f"skip {name}: not built")
            continue
        pins = pip_freeze(venv)
        fname = name.replace("/", "__") + ".freeze.txt"
        (LOCK_DIR / fname).write_text("\n".join(sorted(pins.values())) + "\n")
        manifest["venvs"][name] = {
            "python": first_line(run([str(venv_python(venv)), "--version"])).replace("Python ", ""),
            "freeze": fname,
        }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {MANIFEST.relative_to(ROOT)} and {len(manifest['venvs'])} freeze files. Commit config/env-lock/.")


def rec(level: str, what: str, detail: str = "") -> None:
    results.append((level, what, detail))


def check_system(ref: dict) -> None:
    hw, ref_hw = hardware(), ref["hardware"]
    for k in ("macos", "arch", "chip", "ram_gb"):
        # Not fixable by this tool: informational only.
        rec(OK if hw[k] == ref_hw[k] else WARN, f"hardware {k}", f"yours={hw[k]} reference={ref_hw[k]} (cannot be changed)")

    tools, ref_tools = tool_versions(), ref["tools"]
    for k, want in ref_tools.items():
        have = tools.get(k, "")
        if have == want:
            rec(OK, k, have)
        elif not have:
            rec(BAD, k, f"missing, reference {want}")
            if k in FORMULAS and Path(BREW).exists():
                fixes.append((f"brew install {FORMULAS[k]}", [BREW, "install", FORMULAS[k]], 1800))
        elif k in BUILD_ONLY:
            # Builds the GUI bundle (committed) or DeepFilterNet's native lib;
            # never runs in the pipeline, so a different version cannot change output.
            rec(WARN, k, f"yours={have} reference={want} (build-time only, does not affect runs)")
        elif have.split(".")[0] == want.split(".")[0]:
            # Same major line; Homebrew serves only its current release, so the patch cannot be pinned.
            rec(WARN, k, f"yours={have} reference={want} (same major; Homebrew cannot pin an exact patch)")
        else:
            major = want.split(".")[0]
            formula = FORMULAS.get(k, k)
            versioned = f"{formula.split('@')[0]}@{major}"
            rec(BAD, k, f"yours={have} reference={want}: install the {major}.x line with Homebrew's {versioned}")
            if k in FORMULAS and k != "python3.12" and Path(BREW).exists():
                # brew upgrade can never go down a major version; switch to the
                # versioned keg instead (undo: brew unlink {versioned} && brew link {formula}).
                base = formula.split("@")[0]
                fixes.append((f"brew install {versioned}", [BREW, "install", versioned], 1800))
                fixes.append((f"brew unlink {base}", [BREW, "unlink", base], 300))
                fixes.append(
                    (f"brew link --force --overwrite {versioned}", [BREW, "link", "--force", "--overwrite", versioned], 300)
                )


def check_venvs(ref: dict, prune: bool) -> None:
    for name, info in ref["venvs"].items():
        venv = VENVS.get(name, ROOT / name)
        if not venv_python(venv).exists():
            rec(BAD, f"{name}", "venv missing: run ./scripts/bootstrap_venv.sh first")
            continue
        py_have = first_line(run([str(venv_python(venv)), "--version"])).replace("Python ", "")
        if py_have.split(".")[:2] != info["python"].split(".")[:2]:
            rec(BAD, f"{name} python", f"yours={py_have} reference={info['python']}: delete the venv and re-run bootstrap")
            continue
        want = {}
        for line in (LOCK_DIR / info["freeze"]).read_text().splitlines():
            m = re.match(r"^(?:-e )?(?:git\+\S+#egg=|)([A-Za-z0-9_.-]+)", line)
            if m:
                want[norm(m.group(1))] = line
        have = pip_freeze(venv)
        wrong = [k for k in want if have.get(k) != want[k]]
        extra = [k for k in have if k not in want]
        if not wrong and not extra:
            rec(OK, f"{name} packages", f"{len(want)} match")
            continue
        for k in wrong[:8]:
            rec(BAD, f"{name}: {k}", f"yours={have.get(k, 'missing')} reference={want[k]}")
        if len(wrong) > 8:
            rec(BAD, f"{name}", f"... and {len(wrong) - 8} more differing packages")
        if extra:
            rec(WARN, f"{name}", f"{len(extra)} extra packages not in reference (e.g. {', '.join(extra[:4])})")
        if wrong:
            req = LOCK_DIR / info["freeze"]
            fixes.append((f"pip install exact reference set into {name}", [str(venv_python(venv)), "-m", "pip", "install", "-r", str(req)], PIP_TIMEOUT))
        if prune and extra:
            fixes.append((f"pip uninstall {len(extra)} extra packages from {name}", [str(venv_python(venv)), "-m", "pip", "uninstall", "-y", *extra], PIP_TIMEOUT))


# Native or editable builds that pip freeze cannot see (e.g. DeepFilterNet's Rust df module).
RUNTIME_IMPORTS = {
    "ASSETS/local_deepfilter/venv": "df.enhance",
    "ASSETS/local_mmaudio/venv": "mmaudio",
    "ASSETS/local_musicgen/venv": "transformers",
    "ASSETS/local_speech/venv": "mlx_audio",
    "ASSETS/local_chatterbox/venv": "chatterbox",
    "ASSETS/local_llm/venv": "mlx_lm",
}


def check_runtime_imports() -> None:
    broken = []
    for name, module in RUNTIME_IMPORTS.items():
        py = venv_python(ROOT / name)
        if not py.exists():
            continue  # reported by check_venvs
        if subprocess.run([str(py), "-c", f"import {module}"], capture_output=True, timeout=300).returncode == 0:
            rec(OK, f"{name} import {module}")
        else:
            rec(BAD, f"{name} import {module}", "fails: the runtime build is incomplete")
            broken.append(name)
    if broken:
        fixes.append(("re-run ./scripts/bootstrap_venv.sh to rebuild local runtimes", ["bash", str(ROOT / "scripts" / "bootstrap_venv.sh")], 7200))


def check_models(ref: dict) -> None:
    mine = hf_models()
    for repo, rev in ref["models"].items():
        if mine.get(repo) == rev:
            rec(OK, f"model {repo}", rev[:10])
        else:
            rec(BAD, f"model {repo}", f"yours={mine.get(repo, 'missing')[:10]} reference={rev[:10]}")
            py = venv_python(ROOT / "ASSETS" / "local_musicgen" / "venv")
            if py.exists():
                code = (
                    "from huggingface_hub import snapshot_download as s;"
                    f"s({repo!r}, revision={rev!r}, cache_dir={str(HF_CACHES[0].parent / 'hub')!r})"
                )
                fixes.append((f"download {repo} @ {rev[:10]} (large)", [str(py), "-c", code], MODEL_TIMEOUT))
    rec(WARN, "other models", "weights fetched on first use (e.g. MMAudio) are not pinned by this tool")


def apply_fixes(yes: bool) -> None:
    for desc, argv, timeout in fixes:
        if not yes and input(f"\nRun: {desc}? [y/N] ").strip().lower() != "y":
            print("  skipped")
            continue
        print(f"\n>> {desc}")
        try:
            rc = subprocess.run(argv, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            rc = -1
            print(f"  timed out after {timeout}s")
        print("  done" if rc == 0 else f"  FAILED (exit {rc})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", choices=["check", "snapshot"], default="check")
    ap.add_argument("--fix", action="store_true", help="align this machine with the reference")
    ap.add_argument("--yes", action="store_true", help="do not prompt before each fix")
    ap.add_argument("--prune", action="store_true", help="with --fix, uninstall pip packages not in the lock")
    a = ap.parse_args()

    if a.command == "snapshot":
        snapshot()
        return 0
    if not MANIFEST.exists():
        print(f"No reference found at {MANIFEST.relative_to(ROOT)}. Pull the latest repo, or run 'snapshot' on the reference Mac.")
        return 2

    ref = json.loads(MANIFEST.read_text())
    check_system(ref)
    check_venvs(ref, a.prune)
    check_runtime_imports()
    check_models(ref)
    for level, what, detail in results:
        print(f"[{level}] {what}: {detail}")
    bad = sum(1 for r in results if r[0] == BAD)
    print(f"\n{bad} mismatch(es), {sum(1 for r in results if r[0] == WARN)} warning(s).")
    if a.fix and fixes:
        apply_fixes(a.yes)
        print("\nRe-run without --fix to confirm everything matches.")
    elif fixes:
        print("Run again with --fix to align automatically.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
