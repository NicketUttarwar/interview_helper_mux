#!/usr/bin/env python3
"""Throwaway stage-1 harness: novel|1080 same-speaker pair test.

Not a pipeline module. Preloads local MLX S2S (spoken YES/NO instruction),
cuts exec_510 clips, re-diarizes the concat with Sortformer, writes JSON.
Does not patch transcript/full.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SOURCE_WAV = REPO / "ASSETS/input/mohan_uttarwar_podcast_transforming_cancer_science_direct.wav"
SPEECH_PY = REPO / "ASSETS/local_speech/venv/bin/python"
WORK = REPO / "ASSETS/local_speech/pair_test_novel_1080"
REF_WAV = REPO / "ASSETS/local_speech/warmup_voice/neutral.wav"
INTERROGATE = REPO / "tools/s2s_interrogate.py"
SIDECAR_PY = WORK / "vad_venv" / "bin" / "python"

NOVEL_END_MS = 1785600
PANEL_START_MS = 1786720
CLIP_A = (NOVEL_END_MS - 4000, NOVEL_END_MS)
CLIP_B = (PANEL_START_MS, PANEL_START_MS + 4000)
SILENCE_MS = 300
S2S_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"
DIAR_MODEL = "mlx-community/diar_sortformer_4spk-v1-fp32"
STT_MODEL = "mlx-community/whisper-large-v3-turbo"

PROMPT = (
    "Listen to the first talker clip then the second talker clip. "
    "Answer YES or NO only. "
    "YES if this is the same speaker continuing one thought and diarization was wrong "
    "to label them as two people. "
    "NO if these are two different speakers taking a real turn."
)


def _run(cmd: list[str], *, timeout: int, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd or REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def extract_clip(src: Path, dest: Path, start_ms: int, end_ms: int) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    start_s = start_ms / 1000.0
    dur_s = max((end_ms - start_ms) / 1000.0, 0.05)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_s:.3f}", "-i", str(src),
        "-t", f"{dur_s:.3f}",
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
        str(dest),
    ]
    proc = _run(cmd, timeout=60)
    return {
        "ok": dest.is_file() and dest.stat().st_size > 44 and proc.returncode == 0,
        "path": str(dest),
        "start_ms": start_ms,
        "end_ms": end_ms,
        "returncode": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def concat_pair(a: Path, b: Path, dest: Path, silence_ms: int) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    sil_s = max(silence_ms, 1) / 1000.0
    cmd = [
        "ffmpeg", "-y",
        "-i", str(a),
        "-f", "lavfi", "-t", f"{sil_s:.3f}", "-i", "anullsrc=r=48000:cl=mono",
        "-i", str(b),
        "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
        "-map", "[out]",
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
        str(dest),
    ]
    proc = _run(cmd, timeout=60)
    return {
        "ok": dest.is_file() and dest.stat().st_size > 44 and proc.returncode == 0,
        "path": str(dest),
        "returncode": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-400:],
        "silence_ms": silence_ms,
    }


def warmup_s2s(out_wav: Path) -> dict[str, Any]:
    if not SPEECH_PY.is_file():
        return {"ok": False, "error": f"missing speech venv python: {SPEECH_PY}"}
    if not REF_WAV.is_file():
        return {"ok": False, "error": f"missing warmup ref: {REF_WAV}"}
    payload = {
        "mode": "warmup",
        "text": PROMPT,
        "out_wav": str(out_wav),
        "model_id": S2S_MODEL,
        "ref_audio": str(REF_WAV),
        "timeout_sec": 600,
    }
    proc = subprocess.run(
        [str(SPEECH_PY), str(INTERROGATE), "--mode", "warmup"],
        input=json.dumps(payload),
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=720,
        check=False,
    )
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {"ok": False, "error": "invalid JSON from s2s_interrogate warmup"}
    parsed["returncode"] = proc.returncode
    parsed["stderr_tail"] = (proc.stderr or "")[-600:]
    parsed["prompt"] = PROMPT
    parsed["s2s_model_id"] = S2S_MODEL
    if out_wav.is_file():
        parsed["out_wav"] = str(out_wav)
        parsed["bytes"] = out_wav.stat().st_size
    return parsed


def _sortformer_python() -> Path:
    for py in (SPEECH_PY, SIDECAR_PY):
        if not py.is_file():
            continue
        probe = _run(
            [str(py), "-c", "from mlx_audio.vad import load; print('ok')"],
            timeout=60,
        )
        if probe.returncode == 0 and "ok" in (probe.stdout or ""):
            return py
    return SPEECH_PY


def sortformer_pair(concat_wav: Path, split_ms: int) -> dict[str, Any]:
    py = _sortformer_python()
    helper = WORK / "_sortformer_once.py"
    helper.write_text(
        "import json, sys\n"
        "from mlx_audio.vad import load\n"
        "wav, model_id, split_s, thresh = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])\n"
        "model = load(model_id)\n"
        "result = model.generate(wav, threshold=thresh, min_duration=0.15, merge_gap=0.4)\n"
        "segs = []\n"
        "for seg in (getattr(result, 'segments', None) or []):\n"
        "    speaker = getattr(seg, 'speaker', None)\n"
        "    if speaker is None and isinstance(seg, dict):\n"
        "        speaker = seg.get('speaker') or seg.get('speaker_id')\n"
        "    start = getattr(seg, 'start', None)\n"
        "    end = getattr(seg, 'end', None)\n"
        "    if isinstance(seg, dict):\n"
        "        start = seg.get('start') if start is None else start\n"
        "        end = seg.get('end') if end is None else end\n"
        "    segs.append({'speaker': str(speaker), 'start_s': float(start or 0), 'end_s': float(end or 0)})\n"
        "print(json.dumps({'ok': True, 'text': str(getattr(result, 'text', '') or '')[:500], 'segments': segs}))\n",
        encoding="utf-8",
    )
    proc = _run(
        [
            str(py),
            str(helper),
            str(concat_wav),
            DIAR_MODEL,
            f"{split_ms / 1000.0:.3f}",
            "0.4",
        ],
        timeout=900,
        cwd=WORK,
    )
    if proc.returncode != 0:
        err = ((proc.stderr or proc.stdout or "") + "")[-800:]
        return {
            "ok": False,
            "error": f"sortformer generate failed: {err or proc.returncode}",
            "python": str(py),
            "model_id": DIAR_MODEL,
        }
    try:
        raw = json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "invalid JSON from sortformer helper",
            "stdout_tail": (proc.stdout or "")[-400:],
            "stderr_tail": (proc.stderr or "")[-400:],
            "python": str(py),
        }

    segs = [s for s in (raw.get("segments") or []) if isinstance(s, dict)]
    split_s = split_ms / 1000.0
    left = [s for s in segs if float(s.get("start_s") or 0) < split_s - 0.05]
    right = [s for s in segs if float(s.get("end_s") or 0) > split_s + 0.05]
    left_ids = sorted({str(s.get("speaker")) for s in left})
    right_ids = sorted({str(s.get("speaker")) for s in right})
    all_ids = sorted({str(s.get("speaker")) for s in segs})

    if not segs:
        verdict, reason = "failed", "sortformer returned no segments"
    elif len(all_ids) <= 1 and all_ids:
        verdict, reason = "YES", "one speaker on the concatenated pair"
    elif left_ids and right_ids and set(left_ids) == set(right_ids) and len(left_ids) == 1:
        verdict, reason = "YES", "same sortformer speaker id on both sides of the join"
    elif left_ids and right_ids and set(left_ids).isdisjoint(set(right_ids)):
        verdict, reason = "NO", "different sortformer speaker ids on each side of the join"
    else:
        verdict, reason = "failed", "ambiguous overlap of speaker ids across the join"

    return {
        "ok": verdict in {"YES", "NO"},
        "verdict": verdict,
        "reason": reason,
        "model_id": DIAR_MODEL,
        "python": str(py),
        "text": str(raw.get("text") or "")[:500],
        "segments": segs[:40],
        "left_speakers": left_ids,
        "right_speakers": right_ids,
        "split_s": split_s,
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def stt_clip(clip: Path) -> dict[str, Any]:
    if not SPEECH_PY.is_file():
        return {"ok": False, "error": "missing speech venv"}
    payload = {
        "mode": "classify",
        "listen_mode": "stt_listen",
        "clip_wav": str(clip),
        "interrogate_model_id": STT_MODEL,
        "output_contract": "YES_NO",
        "probe_id": "pair_test.same_speaker",
    }
    proc = subprocess.run(
        [str(SPEECH_PY), str(INTERROGATE), "--mode", "classify"],
        input=json.dumps(payload),
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    try:
        parsed = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {"ok": False, "error": "invalid JSON from classify"}
    parsed["returncode"] = proc.returncode
    parsed["stderr_tail"] = (proc.stderr or "")[-300:]
    return parsed


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    out: dict[str, Any] = {
        "fixture": {
            "execution": "exec_510_d19c15b58ab4_20260819T212734Z",
            "source_wav": str(SOURCE_WAV),
            "novel_end_ms": NOVEL_END_MS,
            "panel_start_ms": PANEL_START_MS,
            "gap_ms": PANEL_START_MS - NOVEL_END_MS,
            "clip_a_ms": list(CLIP_A),
            "clip_b_ms": list(CLIP_B),
            "shipped_labels": {"novel": "spk_1", "1080": "spk_0"},
        },
        "preload_ran": False,
        "interrogate_ran": False,
        "verdict": "failed",
    }
    if not SOURCE_WAV.is_file():
        out["error"] = f"missing source wav: {SOURCE_WAV}"
        (WORK / "result.json").write_text(json.dumps(out, indent=2) + "\n")
        print(json.dumps(out, indent=2))
        return 1

    a_wav = WORK / "clip_a_novel.wav"
    b_wav = WORK / "clip_b_1080.wav"
    concat_wav = WORK / "concat_pair.wav"
    warmup_wav = WORK / "s2s_preload_question.wav"

    out["clip_a"] = extract_clip(SOURCE_WAV, a_wav, CLIP_A[0], CLIP_A[1])
    out["clip_b"] = extract_clip(SOURCE_WAV, b_wav, CLIP_B[0], CLIP_B[1])
    a_dur = CLIP_A[1] - CLIP_A[0]
    out["concat"] = concat_pair(a_wav, b_wav, concat_wav, SILENCE_MS)

    out["verify"] = {"speech_python": str(SPEECH_PY), "exists": SPEECH_PY.is_file()}
    if SPEECH_PY.is_file():
        vproc = _run([str(SPEECH_PY), str(INTERROGATE), "--verify"], timeout=60)
        try:
            out["verify"]["interrogate"] = json.loads(vproc.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError:
            out["verify"]["interrogate"] = {
                "ok": False,
                "stdout_tail": (vproc.stdout or "")[-300:],
                "stderr_tail": (vproc.stderr or "")[-300:],
            }

    out["s2s_warmup"] = warmup_s2s(warmup_wav)
    out["preload_ran"] = bool(out["s2s_warmup"].get("ok"))

    if out["concat"].get("ok"):
        out["sortformer"] = sortformer_pair(concat_wav, a_dur + SILENCE_MS)
        out["interrogate_ran"] = bool(out["sortformer"].get("ok") or out["sortformer"].get("verdict"))
        out["verdict"] = str(out["sortformer"].get("verdict") or "failed")
        out["reason"] = out["sortformer"].get("reason") or out["sortformer"].get("error")
    else:
        out["error"] = "concat failed; skip sortformer"
        out["verdict"] = "failed"

    out["stt_clip_a"] = stt_clip(a_wav) if out["clip_a"].get("ok") else {"ok": False}
    out["stt_clip_b"] = stt_clip(b_wav) if out["clip_b"].get("ok") else {"ok": False}

    result_path = WORK / "result.json"
    result_path.write_text(json.dumps(out, indent=2) + "\n")
    out["result_json"] = str(result_path)
    print(
        json.dumps(
            {
                k: out[k]
                for k in ("verdict", "reason", "preload_ran", "interrogate_ran", "result_json")
                if k in out
            },
            indent=2,
        )
    )
    return 0 if out.get("verdict") in {"YES", "NO"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
