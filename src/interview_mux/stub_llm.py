"""Offline stand-in for the OpenAI chat API, for keyless pipeline traversal.

Enabled with ``MUX_STUB_LLM=1``. When unset, nothing here is imported and the
production path is byte-identical.

Why intercept at the client rather than higher up: every layer around the call
then still runs for real. Prompt assembly, model resolution, response-format
selection, envelope normalisation, schema validation, the retry ladder and the
call recorder all execute exactly as they would against OpenAI. Only the network
hop is replaced. That makes a keyless run a genuine test of the pipeline's own
plumbing rather than a mock of it.

The reply is generated **from the schema the stage itself asked for**
(``response_format.json_schema.schema``), so it is structurally valid by
construction. Where a field looks like an identifier, real ids are pulled from
the run's own artifacts so cross-artifact validators have a chance of passing;
see ``_IdHints``. This produces structurally valid, semantically meaningless
output: it proves a stage runs, writes and validates, and proves nothing about
quality.
"""

from __future__ import annotations

import json
import os
import sys
import re
from pathlib import Path
from typing import Any

STUB_ENV = "MUX_STUB_LLM"
#: Optional JSON file of extra hints: {"segment_ids": [...], "speaker_ids": [...]}.
HINTS_ENV = "MUX_STUB_LLM_HINTS"


def stub_enabled() -> bool:
    return str(os.environ.get(STUB_ENV) or "").strip().lower() in {"1", "true", "yes"}


# --- identifier hints -------------------------------------------------------


class _IdHints:
    """Real ids from the current run, so generated refs can satisfy validators."""

    def __init__(self) -> None:
        self.segment_ids: list[str] = []
        self.speaker_ids: list[str] = []
        self._turns: list[tuple[int, int, str]] | None = None
        self._stamp: tuple[Any, ...] = ()
        self._explicit = False
        self._loaded = False

    def load(self) -> None:
        # An explicit hints file is read once and wins outright.
        if not self._loaded:
            self._loaded = True
            extra = str(os.environ.get(HINTS_ENV) or "").strip()
            if extra and Path(extra).is_file():
                try:
                    doc = json.loads(Path(extra).read_text(encoding="utf-8"))
                    self.segment_ids = [str(x) for x in (doc.get("segment_ids") or [])]
                    self.speaker_ids = [str(x) for x in (doc.get("speaker_ids") or [])]
                    self._explicit = bool(self.segment_ids or self.speaker_ids)
                except (OSError, json.JSONDecodeError):
                    pass
        if self._explicit:
            return
        # Everything below is a cheap stat of three files and must run on every
        # call: a once-only latch here is what fed missing_framing a one-segment
        # manifest three times after the real one had grown to four.
        # The run's artifacts evolve under us: boundary_detection writes a
        # manifest with one segment, boundary_topic_resplit rewrites it with
        # four, and repairs flip roles in speakers.json. A once-only cache
        # therefore answered missing_framing with the one segment it had seen
        # first, three times in a row. Refresh whenever any source file changes.
        try:
            from interview_mux.run_context import RunContext

            rid = str(os.environ.get("MUX_RUN_ID") or "").strip()
            ctx = RunContext(rid, create=False) if rid else None
            if ctx is None:
                return
            stamp = tuple(
                (rel, self._mtime(ctx, rel))
                for rel in (
                    "segments/manifest.json",
                    "understanding/speakers.json",
                    "transcript/full.json",
                )
            )
            if stamp == self._stamp and (self.segment_ids or self.speaker_ids):
                return
            self._stamp = stamp
            self.segment_ids = []
            self.speaker_ids = []
            self._turns = None
            man = self._read(ctx, "segments/manifest.json")
            if not self.segment_ids and man:
                self.segment_ids = [
                    str(s.get("segment_id"))
                    for s in (man.get("segments") or [])
                    if isinstance(s, dict) and s.get("segment_id")
                ]
            spk = self._read(ctx, "understanding/speakers.json")
            if not self.speaker_ids and spk:
                self.speaker_ids = [
                    str(s.get("speaker_id"))
                    for s in (spk.get("speakers") or [])
                    if isinstance(s, dict) and s.get("speaker_id")
                ]
            # speakers.json is itself a stub output, so for speaker_roles (which
            # produces it) there is nothing to learn from. The transcript is the
            # real source: diarization has already labelled every word.
            if not self.speaker_ids:
                self.speaker_ids = self._speakers_from_transcript(ctx)
        except Exception:
            # Hints are a nicety; a stub reply without them is still schema-valid.
            pass

    @staticmethod
    def _final(ctx: Any, rel: str) -> Any:
        """Committed artifact path. Never the staging copy.

        Inside a staged stage, ctx.read_path resolves through .pending_writes for
        that stage, where an upstream artifact does not exist. Hints want the
        committed truth on disk, so they resolve past the redirect.
        """
        parts = rel.split("/")
        try:
            staged = ctx.read_path(*parts)
            if staged.is_file():
                return staged  # the running stage's own rewrite, not yet committed
        except Exception:
            pass
        return ctx.final_path(*parts)

    @classmethod
    def _read(cls, ctx: Any, rel: str) -> dict[str, Any]:
        try:
            path = cls._final(ctx, rel)
            if not path.is_file():
                return {}
            doc = json.loads(path.read_text(encoding="utf-8"))
            return doc if isinstance(doc, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _mtime(cls, ctx: Any, rel: str) -> float:
        try:
            return cls._final(ctx, rel).stat().st_mtime
        except Exception:
            return -1.0

    @staticmethod
    def _speakers_from_transcript(ctx: Any) -> list[str]:
        """Diarized speakers worth modelling, most talkative first.

        Diarization emits spurious labels: a 120s excerpt of a two-person
        interview came back as spk_0 (185 words), spk_1 (**1 word**) and spk_2
        (107 words). Treating that as three participants is what starved the
        role-dependent stages, so anything under 2% of the words is dropped as an
        artefact rather than being handed downstream as a speaker.
        """
        doc = _IdHints._read(ctx, "transcript/full.json")
        if not doc:
            return []
        counts: dict[str, int] = {}
        first_seen: dict[str, int] = {}
        for w in doc.get("words") or []:
            if not isinstance(w, dict):
                continue
            sid = str(w.get("speaker_id") or w.get("speaker") or "").strip()
            if not sid:
                continue
            counts[sid] = counts.get(sid, 0) + 1
            try:
                start = int(float(w.get("start_ms") or w.get("start") or 0))
            except (TypeError, ValueError):
                start = 0
            first_seen.setdefault(sid, start)
        total = sum(counts.values())
        if not total:
            return []
        # Index 0 becomes the interviewer, and segment_classification then
        # retypes every segment from the roster, so the interviewer must be the
        # speaker the first segment actually belongs to: whoever talks first.
        keep = [sid for sid, n in counts.items() if n >= max(2, total * 0.02)]
        keep.sort(key=lambda sid: (first_seen.get(sid, 0), sid))
        return keep

    def turns(self) -> list[tuple[int, int, str]]:
        """Real speaker turns (start_ms, end_ms, speaker_id) tiling the tape.

        Consecutive same-speaker words merge into one turn; turns under two
        seconds fold into the previous one so a stray label cannot produce a
        sliver. This is what boundary rows are cut from, so the stub's
        segmentation covers the whole recording and alternates speakers the way
        the tape actually does, instead of a handful of 4-second windows that
        boundary_detection rightly rejects as coarse.
        """
        self.load()
        if self._turns is not None:
            return self._turns
        self._turns = []
        try:
            from interview_mux.run_context import RunContext

            rid = str(os.environ.get("MUX_RUN_ID") or "").strip()
            ctx = RunContext(rid, create=False) if rid else None
            if ctx is None:
                return self._turns
            doc = self._read(ctx, "transcript/full.json")
            if not doc:
                return self._turns
        except Exception:
            return self._turns
        keep = set(self.speaker_ids)
        raw: list[list[Any]] = []
        for w in doc.get("words") or []:
            if not isinstance(w, dict):
                continue
            sid = str(w.get("speaker_id") or w.get("speaker") or "").strip()
            if keep and sid not in keep:
                continue
            try:
                st = int(float(w.get("start_ms") or w.get("start") or 0))
                en = int(float(w.get("end_ms") or w.get("end") or st))
            except (TypeError, ValueError):
                continue
            if raw and raw[-1][2] == sid:
                raw[-1][1] = max(raw[-1][1], en)
            else:
                raw.append([st, en, sid])
        merged: list[list[Any]] = []
        for st, en, sid in raw:
            if merged and (en - st) < 2000:
                merged[-1][1] = max(merged[-1][1], en)
            else:
                merged.append([st, en, sid])
        # Close the gaps so the windows tile: each turn runs to the next start.
        for i in range(len(merged) - 1):
            merged[i][1] = max(merged[i][1], merged[i + 1][0])
        self._turns = [(int(a), int(b), str(c)) for a, b, c in merged][:24]
        return self._turns

    def count(self) -> int:
        """How many speakers the tape actually has, as far as we can tell."""
        self.load()
        return len(self.speaker_ids)

    def segment(self, index: int = 0) -> str:
        self.load()
        if self.segment_ids:
            return self.segment_ids[index % len(self.segment_ids)]
        return f"seg_{index + 1:03d}"

    def speaker(self, index: int = 0) -> str:
        self.load()
        if self.speaker_ids:
            return self.speaker_ids[index % len(self.speaker_ids)]
        return f"spk_{index}"


_HINTS = _IdHints()

#: Total tape length the stub pretends to work over, in ms.
DURATION_ENV = "MUX_STUB_AUDIO_MS"

_TIME_FIELDS_START = ("start_ms", "from_ms", "at_ms", "offset_ms", "begin_ms", "in_ms")
_TIME_FIELDS_END = ("end_ms", "to_ms", "out_ms", "until_ms")
_TIME_FIELDS_SPAN = ("duration_ms", "length_ms", "span_ms")


class _TimeCursor:
    """Hands out increasing, non-empty [start, end) windows inside the tape.

    A schema-only generator emits 0 for every integer, which makes every window
    zero-length. Stages then drop those rows as degenerate and a required
    non-empty array validates as empty, which stops a traversal for a reason
    that has nothing to do with the code under test.
    """

    def __init__(self) -> None:
        self.pos = 1000
        self.span = 4000
        self.last_start = 1000
        self.last_end = 5000

    def reset(self) -> None:
        self.pos = 1000
        self.last_start = 1000
        self.last_end = 5000

    @property
    def total(self) -> int:
        try:
            return max(20000, int(str(os.environ.get(DURATION_ENV) or "").strip() or 0))
        except ValueError:
            return 120000

    def start(self) -> int:
        total = self.total
        if self.pos + self.span * 2 > total:
            self.pos = 1000  # wrap rather than run off the end of the tape
        self.last_start = self.pos
        self.last_end = self.pos + self.span
        self.pos += self.span
        return self.last_start

    def end(self) -> int:
        # end_ms usually follows start_ms in property order, so reuse the window.
        return self.last_end

    def span_ms(self) -> int:
        return self.span


_CURSOR = _TimeCursor()

_SEGMENT_FIELD = re.compile(r"segment_ids?$|^segment_id|_segment_id$|targets?_segment_id")
_SPEAKER_FIELD = re.compile(r"speaker_id$|^speaker_id")


def _string_for(field: str, index: int = 0) -> str:
    """A plausible string for a field name, preferring real ids.

    ``index`` is the row this value belongs to, so row N of an output array gets
    segment N and speaker N instead of every row naming the first one. Rows that
    all claim the same speaker read as one participant talking to themselves,
    which the role and gap stages then refuse.
    """
    low = field.lower()
    if _SEGMENT_FIELD.search(low):
        return _HINTS.segment(index)
    if _SPEAKER_FIELD.search(low):
        return _HINTS.speaker(index)
    if low.endswith("_ms"):
        return str(_CURSOR.start())
    if low.endswith("_sec"):
        return "4"
    if "id" == low or low.endswith("_id"):
        return f"stub_{low}"
    return "stub"


#: Roles that count as "this speaker frames the conversation". A speakers.json
#: without one of these blocks content_context and every stage behind it with
#: "speakers.json missing frame role (interviewer/moderator/co_host)".
_FRAME_ROLES = ("interviewer", "moderator", "co_host")
_GUEST_ROLES = ("interviewee", "guest", "subject")


def _pick_role(prop: dict[str, Any], preferred: tuple[str, ...]) -> str | None:
    """First preferred role the schema will accept, or None to leave it alone."""
    enum = prop.get("enum")
    if isinstance(enum, list) and enum:
        allowed = {str(v) for v in enum if v is not None}
        for role in preferred:
            if role in allowed:
                return role
        return None
    # No enum: any string goes.
    return preferred[0] if preferred else None


def _fix_speaker_row(out: dict[str, Any], props: dict[str, Any], index: int) -> None:
    """Make row ``index`` describe a real speaker, and row 0 frame the interview.

    Generic schema filling gives every row the same speaker and whatever role
    happens to sit first in the enum. That produced a one_on_one profile listing a
    single "interviewee" and no interviewer, so the run stopped at
    content_context. Naming the actual diarized speakers and making the first one
    the interviewer costs nothing and keeps the shape schema-valid.
    """
    if "speaker_id" in out:
        out["speaker_id"] = _HINTS.speaker(index)
    for name in ("role", "speaker_role"):
        prop = props.get(name)
        if not isinstance(prop, dict):
            continue
        wanted = _FRAME_ROLES if index == 0 else _GUEST_ROLES
        role = _pick_role(prop, wanted)
        if role is not None:
            out[name] = role


#: Segment types that count as the host framing the conversation. A manifest with
#: none of these, while speakers.json names a host, is refused as
#: "starved_host_packet" and blocks missing_framing and everything behind it.
_HOST_SEGMENT_TYPES = ("interviewer_question", "interviewer_prompt", "host_turn")


def _fix_segment_row(out: dict[str, Any], props: dict[str, Any], index: int) -> None:
    """Let the first segment be the host speaking, so the manifest matches the roster.

    The two are generated independently, so the roster could name an interviewer
    while every segment came out as the guest talking. That pair is internally
    inconsistent, and the preflight is right to refuse it.
    """
    if index != 0:
        return
    for name in ("type", "segment_type"):
        prop = props.get(name)
        if not isinstance(prop, dict):
            continue
        enum = prop.get("enum")
        if isinstance(enum, list) and enum:
            allowed = {str(v) for v in enum if v is not None}
            for kind in _HOST_SEGMENT_TYPES:
                if kind in allowed:
                    out[name] = kind
                    return
            return
        out[name] = _HOST_SEGMENT_TYPES[0]
        return


def _is_window_row(props: dict[str, Any]) -> bool:
    return any(k in props for k in _TIME_FIELDS_START) and any(
        k in props for k in _TIME_FIELDS_END
    )


def _fix_window_row(out: dict[str, Any], props: dict[str, Any], index: int) -> None:
    """Give a time-window row the real turn at ``index``."""
    turns = _HINTS.turns()
    if not turns:
        return
    st, en, sid = turns[index % len(turns)]
    for k in _TIME_FIELDS_START:
        if k in out:
            out[k] = st
    for k in _TIME_FIELDS_END:
        if k in out:
            out[k] = en
    for k in _TIME_FIELDS_SPAN:
        if k in out:
            out[k] = max(1, en - st)
    if "speaker_id" in out:
        out["speaker_id"] = sid


# --- schema to instance -----------------------------------------------------


#: How many rows to emit for a stage's top-level output arrays.
FANOUT_ENV = "MUX_STUB_ARRAY_ITEMS"


def _array_fanout() -> int:
    """Rows to emit for a stage's top-level output arrays. Default 1.

    Raising this was tried against the real gates and made things worse, not
    better: 8 rows got boundary_detection past nothing (its reject is computed
    from coverage and duration, not row count) and broke segment_classification,
    which had been passing with 1. Left as a knob for probing a specific stage,
    but 1 is the setting that gets furthest.
    """
    try:
        n = int(str(os.environ.get(FANOUT_ENV) or "").strip() or 0)
    except ValueError:
        n = 0
    return max(1, min(24, n or 1))

def _resolve_ref(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return schema
    node: Any = root
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            return schema
        node = node[part]
    return node if isinstance(node, dict) else schema


def _types_of(schema: dict[str, Any]) -> list[str]:
    t = schema.get("type")
    if isinstance(t, str):
        return [t]
    if isinstance(t, list):
        return [str(x) for x in t]
    if "properties" in schema:
        return ["object"]
    if "items" in schema:
        return ["array"]
    if "enum" in schema:
        return ["string"]
    return ["string"]


def schema_instance(
    schema: dict[str, Any],
    *,
    field: str = "",
    root: dict[str, Any] | None = None,
    depth: int = 0,
    index: int = 0,
) -> Any:
    """Smallest instance satisfying ``schema``. Deterministic, never random."""
    if not isinstance(schema, dict):
        return None
    root = root if root is not None else schema
    schema = _resolve_ref(schema, root)

    for key in ("anyOf", "oneOf", "allOf"):
        branches = schema.get(key)
        if isinstance(branches, list) and branches:
            if key == "allOf":
                merged: dict[str, Any] = {}
                for b in branches:
                    if isinstance(b, dict):
                        merged = {**merged, **_resolve_ref(b, root)}
                return schema_instance(merged, field=field, root=root, depth=depth, index=index)
            # Prefer the first non-null branch so required refs stay populated.
            for b in branches:
                if isinstance(b, dict) and "null" not in _types_of(b):
                    return schema_instance(b, field=field, root=root, depth=depth, index=index)
            return None

    if "const" in schema:
        return schema["const"]

    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        # Prefer a non-null enum member; many of these unions allow null.
        for candidate in enum:
            if candidate is not None:
                return candidate
        return None

    types = _types_of(schema)
    if depth > 12:
        # Runaway recursion guard: satisfy nullable, else the simplest scalar.
        return None if "null" in types else ("stub" if "string" in types else 0)

    if "object" in types:
        props = schema.get("properties")
        props = props if isinstance(props, dict) else {}
        required = schema.get("required")
        # OpenAI structured outputs require every property, so with no explicit
        # `required` the safest reading is "emit them all".
        names = [str(n) for n in required] if isinstance(required, list) else list(props)
        out: dict[str, Any] = {}
        for name in names:
            sub = props.get(name)
            if not isinstance(sub, dict):
                out[name] = None
                continue
            out[name] = schema_instance(
                sub, field=name, root=root, depth=depth + 1, index=index
            )
        if _is_window_row(props):
            _fix_window_row(out, props, index)
        elif "speaker_id" in props:
            _fix_speaker_row(out, props, index)
        if "segment_id" in props:
            _fix_segment_row(out, props, index)
        return out

    if "array" in types:
        items = schema.get("items")
        min_items = int(schema.get("minItems") or 0)
        # Emit at least one element: a great many consumers treat an empty list
        # as "stage produced nothing" and refuse, which would stop the traversal
        # for a reason that has nothing to do with the code under test.
        #
        # One element is often still not enough. Quality gates count rows against
        # the tape (boundary_detection refuses "coarse_or_invalid_segmentation"
        # for a single boundary over a long recording), so fan out the shallow
        # arrays, which are the stage's actual output rows, while keeping deeply
        # nested arrays at one element so the payload cannot explode.
        count = max(1, min_items)
        if depth <= 2:
            count = max(count, _array_fanout())
        # A speaker array should have one row per speaker actually on the tape.
        # Emitting a single row is what produced a speakers.json naming one
        # participant with no interviewer, which blocks every role-dependent
        # stage with "speakers.json missing frame role".
        if isinstance(items, dict):
            item_props = _resolve_ref(items, root).get("properties")
            if isinstance(item_props, dict):
                if _is_window_row(item_props) and depth <= 2:
                    count = max(count, len(_HINTS.turns()))
                elif "speaker_id" in item_props:
                    count = max(count, _HINTS.count())
                elif depth <= 2 and any(_SEGMENT_FIELD.search(k.lower()) for k in item_props):
                    # One row per segment: coverage gates (missing_framing's
                    # sealed_ratio, for one) count segments left untouched.
                    _HINTS.load()
                    count = max(count, min(24, len(_HINTS.segment_ids)))
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and max_items < count:
            count = max_items
        if os.environ.get("MUX_STUB_TRACE"):
            print(
                f"[stub-trace] array field={field!r} depth={depth} count={count} "
                f"max_items={max_items} segs={len(_HINTS.segment_ids)} "
                f"spk={len(_HINTS.speaker_ids)} turns={len(_HINTS.turns())} "
                f"run={os.environ.get('MUX_RUN_ID','')} pid={os.getpid()}",
                file=sys.stderr,
                flush=True,
            )
        if not isinstance(items, dict):
            return []
        return [
            schema_instance(items, field=field, root=root, depth=depth + 1, index=i)
            for i in range(count)
        ]

    if "string" in types:
        text = _string_for(field, index)
        min_len = schema.get("minLength")
        if isinstance(min_len, int) and len(text) < min_len:
            # Pad rather than repeat a single char, so the value still reads as
            # a value in artifacts a human may end up looking at.
            text = (text + " detail") * (min_len // max(1, len(text) + 6) + 1)
            text = text[:min_len] if len(text) > min_len else text.ljust(min_len, "x")
        max_len = schema.get("maxLength")
        if isinstance(max_len, int) and len(text) > max_len:
            text = text[:max_len]
        return text
    if "integer" in types or "number" in types:
        is_int = "integer" in types
        low_field = (field or "").lower()
        if low_field in _TIME_FIELDS_START:
            return _CURSOR.start()
        if low_field in _TIME_FIELDS_END:
            return _CURSOR.end()
        if low_field in _TIME_FIELDS_SPAN:
            return _CURSOR.span_ms()
        if low_field.endswith("_sec") or low_field.endswith("_seconds"):
            return 4 if is_int else 4.0
        if low_field in {"confidence", "score", "weight"}:
            return 1 if is_int else 0.9
        value: float = 0.0
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool):
            value = float(minimum)
        excl_min = schema.get("exclusiveMinimum")
        if isinstance(excl_min, (int, float)) and not isinstance(excl_min, bool):
            # Must be strictly greater, so step past it.
            value = max(value, float(excl_min) + (1 if is_int else 0.1))
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
            value = min(value, float(maximum))
        excl_max = schema.get("exclusiveMaximum")
        if isinstance(excl_max, (int, float)) and not isinstance(excl_max, bool):
            value = min(value, float(excl_max) - (1 if is_int else 0.1))
        return int(value) if is_int else float(value)
    if "boolean" in types:
        return False
    return None


def _schema_from_response_format(response_format: Any) -> dict[str, Any] | None:
    if not isinstance(response_format, dict):
        return None
    js = response_format.get("json_schema")
    if isinstance(js, dict):
        inner = js.get("schema")
        if isinstance(inner, dict):
            return inner
    if isinstance(response_format.get("schema"), dict):
        return response_format["schema"]
    return None


_GENERIC_ENVELOPE: dict[str, Any] = {
    "status": "complete",
    "artifacts": {},
    "memory_updates": {},
    "needs": [],
    "follow_up_investigations": [],
    "confidence": 0.9,
    "reasoning_summary": "stub",
}


def stub_reply_content(kwargs: dict[str, Any]) -> str:
    """The JSON string a stubbed completion returns for these create() kwargs."""
    _CURSOR.reset()
    schema = _schema_from_response_format(kwargs.get("response_format"))
    if schema is None:
        return json.dumps(_GENERIC_ENVELOPE)
    doc = schema_instance(schema)
    if isinstance(doc, dict):
        # Nudge the envelope toward a clean pass so the traversal keeps moving.
        if "status" in doc:
            doc["status"] = "complete"
        if "confidence" in doc and not isinstance(doc.get("confidence"), (int, float)):
            doc["confidence"] = 0.9
    return json.dumps(doc)


# --- the fake client --------------------------------------------------------


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content
        self.role = "assistant"
        self.tool_calls = None
        self.refusal = None


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)
        self.finish_reason = "stop"
        self.index = 0


class _Usage:
    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


class _Completion:
    def __init__(self, content: str, model: str, prompt_chars: int) -> None:
        self.choices = [_Choice(content)]
        self.model = model
        self.id = "stub-completion"
        self.object = "chat.completion"
        self.created = 0
        # Rough 4-chars-per-token estimate; only budget accounting reads this.
        self.usage = _Usage(max(1, prompt_chars // 4), max(1, len(content) // 4))

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": self.choices[0].finish_reason,
                    "message": {"role": "assistant", "content": self.choices[0].message.content},
                }
            ],
            "usage": {
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
                "total_tokens": self.usage.total_tokens,
            },
        }


class _Completions:
    def __init__(self, owner: "StubOpenAI") -> None:
        self._owner = owner

    def create(self, **kwargs: Any) -> _Completion:
        self._owner.calls.append(
            {
                "model": kwargs.get("model"),
                "messages": len(kwargs.get("messages") or []),
                "has_schema": _schema_from_response_format(kwargs.get("response_format"))
                is not None,
            }
        )
        prompt_chars = sum(
            len(str(m.get("content") or "")) for m in (kwargs.get("messages") or [])
        )
        return _Completion(
            stub_reply_content(kwargs), str(kwargs.get("model") or "stub-model"), prompt_chars
        )


class _Chat:
    def __init__(self, owner: "StubOpenAI") -> None:
        self.completions = _Completions(owner)


class StubOpenAI:
    """Minimal stand-in exposing only ``chat.completions.create``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.chat = _Chat(self)
        self.calls: list[dict[str, Any]] = []


__all__ = [
    "HINTS_ENV",
    "STUB_ENV",
    "StubOpenAI",
    "schema_instance",
    "stub_enabled",
    "stub_reply_content",
]
