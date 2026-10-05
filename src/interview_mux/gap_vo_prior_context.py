"""Prior native-segment context for synthetic gap VO LLM calls and density seeds.

Plan 1: every framing line that targets segment S must see the immediate prior
ordered native segment P (text + impact/complete-thought tags) so VO copy stays
courteous after mic-drop moments instead of interruptive density stock.
"""

from __future__ import annotations

import re
import zlib
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

GAP_VO_CONTEXT_AUDIT_REL = "understanding/gap_vo_context_audit.json"

# Interruptive openers forbidden after a complete / impactful prior native close.
INTERRUPTIVE_OPENER_RE = re.compile(
    r"^\s*(let me pause you there|hold on(?: a (?:second|sec|moment))?|stop right there|"
    r"wait(?: a (?:second|sec|moment))?|hang on)\b",
    re.IGNORECASE,
)

_INCOMPLETE_TAIL_TOKENS = frozenset(
    {
        "if",
        "and",
        "but",
        "or",
        "nor",
        "because",
        "that",
        "when",
        "while",
        "so",
        "as",
        "than",
        "to",
        "of",
        "the",
        "a",
        "an",
        "my",
        "our",
        "their",
        "your",
        "his",
        "her",
        "its",
        "this",
        "these",
        "those",
        "i",
        "im",
        "i'm",
        "we",
        "he",
        "she",
        "it",
        "they",
        # Mid-promise / mid-list closers that still need continuation.
        "yet",
        "still",
        "also",
        "just",
        "even",
        "like",
        "with",
        "into",
        "onto",
        "from",
        "about",
        "for",
        "by",
        "at",
        "on",
        "in",
        "up",
        "out",
        "over",
        "under",
        "through",
        "between",
        "among",
        "via",
        "per",
        "without",
        "within",
        "across",
        "toward",
        "towards",
        "upon",
        "against",
        "whether",
        "whose",
        "whom",
        "which",
        "who",
        "how",
        "what",
        "why",
        "versus",
        "vs",
        "including",
        "include",
        "includes",
        "plus",
        "except",
        "unless",
        "although",
        "though",
        "whereas",
        "meanwhile",
        # Auxiliaries / modals left hanging mid-thought.
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "having",
        "do",
        "does",
        "did",
        "can",
        "could",
        "would",
        "should",
        "will",
        "shall",
        "may",
        "might",
        "must",
        "etc",
    }
)

# Multi-word hanging setups — illegal keeper ends even with a following pause.
_HANGING_SETUP_PHRASES: tuple[str, ...] = (
    "that is the time",
    "that was the time",
    "the fact that",
    "in terms of",
    "the reason why",
    "the reason that",
    "how do we",
    "how do you",
    "how do i",
    "what we need to",
    "what you want to",
    "what i want to",
    "the way that",
    "the thing that",
    "so that we",
    "so that you",
    "in order to",
    "as far as",
    "when it comes to",
    "and yet",
    "but still",
    "but then",
    "and then",
    "and also",
    "not only",
    "as well as",
    "such as",
    "for example",
    "for instance",
    # Soft-hang setups (often STT-punctuated) that still need the payoff clause.
    "what is happening",
    "what's happening",
    "interested in",
    "the point is",
    "the key is",
    "which means",
    "that means",
    "in other words",
    "on the other hand",
    "as i said",
    "going to be",
    "supposed to",
    "need to",
    "have to",
    "trying to",
    "want to",
    "able to",
)

# Tokens that are illegal *opens* (segment starts mid-clause / mid-list).
_CONTINUER_OPEN_TOKENS = frozenset(
    {
        "and",
        "or",
        "nor",
        "but",
        "yet",
        "also",
        "then",
        "so",
        "because",
        "which",
        "who",
        "whom",
        "whose",
        "that",
        "than",
        "with",
        "from",
        "into",
        "onto",
        "for",
        "of",
        "to",
        "about",
        "like",
        "including",
        "versus",
        "vs",
        "plus",
        "except",
        "unless",
        "although",
        "though",
        "whereas",
        "meanwhile",
        "at",
        "on",
        "in",
        "up",
        "out",
        "over",
        "under",
        "through",
        "between",
        "among",
        "via",
        "per",
        "without",
        "within",
        "across",
        "toward",
        "towards",
        "upon",
        "against",
    }
)

_HANGING_SETUP_RE = re.compile(
    r"(?:^|\s)(?:"
    + "|".join(re.escape(p) for p in _HANGING_SETUP_PHRASES)
    + r")\s*$",
    re.IGNORECASE,
)

# Tokens that often start a *new* conceptual unit after a hinge (not same-clause continue).
_NEW_UNIT_OPENERS = frozenset(
    {
        "so",
        "then",
        "now",
        "anyway",
        "meanwhile",
        "also",
        "plus",
        "next",
        "later",
        "afterward",
        "afterwards",
        "but",
        "however",
        "still",
        "look",
        "listen",
        "okay",
        "ok",
        "well",
        "right",
    }
)

# Host/other-speaker tokens that often complete the prior speaker's hanging setup.
_BACKCHANNEL_OPEN_TOKENS = frozenset(
    {
        "okay",
        "ok",
        "right",
        "yeah",
        "yep",
        "yup",
        "mm",
        "mhm",
        "mmhmm",
        "uhhuh",
        "uh-huh",
        "alright",
        "allright",
    }
)

# Nested disfluencies (not a real host turn). Used to absorb um/uh inside a monologue.
_FILLED_PAUSE_TOKENS = frozenset(
    {
        "um",
        "uh",
        "ah",
        "er",
        "mm",
        "hmm",
        "hm",
        "mhm",
        "mmhmm",
        "uhhuh",
        "uh-huh",
    }
)

_SUBORDINATE_CLAUSE_OPEN_RE = re.compile(
    r"^(?:if|because|when|while|although|though|unless|until|since|so that|as if)\b",
    re.IGNORECASE,
)

# Same-clause continuation / flip-detection ceiling. Do not retarget spine PAUSE_SPLIT_MS.
CLAUSE_CONTINUE_MAX_GAP_MS = 4000
CROSS_SPEAKER_COMPLETION_GAP_MS = CLAUSE_CONTINUE_MAX_GAP_MS
# STT often abuts the next word at exactly end_ms (clinical|trials). Inclusive
# lookahead must still see that token; a few ms of overlap is the same event.
WORD_ABUT_TOL_MS = 20
ZERO_GAP_HINGE_MS = 150

_DETERMINERS = frozenset({"a", "an", "the"})
_INTENSIFIERS = frozenset({"very", "really", "quite", "highly", "so", "too", "extremely"})
_NOMINAL_ADJECTIVE_RE = re.compile(
    r"^(?:novel|new|unique|specific|particular|interesting|important|"
    r"different|special|critical|essential|available|actionable|"
    r".+(?:al|ive|ous|ic|able|ible|ful|less|ish|ary|ent|ant))$",
    re.IGNORECASE,
)

_MIC_DROP_HINT_RE = re.compile(
    r"\b(higher than|lower than|never|nobody|nothing|realized|truth is|bottom line|"
    r"cash in|account was|that was the|turning point)\b",
    re.IGNORECASE,
)

GAP_FRAMING_PRIOR_STAGES = frozenset(
    {
        "gap_framing_compose",
        "optimal_questions",
        "missing_framing",
    }
)


def prior_context_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = ((cfg or merged_config()).get("analysis") or {}).get("gap_framing") or {}
    block = raw.get("prior_native_context") if isinstance(raw.get("prior_native_context"), dict) else {}
    defaults = {
        "enabled": True,
        "volley_turns_enabled": True,
        "end_window_chars": 420,
        "full_text_max_chars": 900,
        "micro_max_ms": 2000,
        "micro_max_words": 4,
        "impact_min_words": 18,
        "impact_min_duration_ms": 8000,
        "rewrite_density_seeds": True,
        "relocate_micro_targets": True,
    }
    return {**defaults, **block}


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _last_token(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9']+", text or "")
    return words[-1].lower() if words else ""


DEFAULT_PAUSE_SPLIT_MS = 1000


def last_clause_is_subordinate_fragment(text: str) -> bool:
    """True when the last clause is a subordinate leftover even if STT added ``.``."""
    last = last_spoken_sentence(text)
    last = re.sub(r"[.!?…]+$", "", (last or "").strip()).strip()
    if not last:
        return False
    parts = re.split(r",\s*", last)
    clause = (parts[-1] if parts else last).strip()
    return bool(clause and _SUBORDINATE_CLAUSE_OPEN_RE.match(clause))


def is_backchannel_only_text(text: str) -> bool:
    """True when the span is only a backchannel (Okay / Right / Yeah / um)."""
    toks = re.findall(r"[A-Za-z0-9']+", text or "")
    if not toks:
        return False
    return all(t.lower() in _BACKCHANNEL_OPEN_TOKENS for t in toks)


def is_filled_pause_only_text(text: str) -> bool:
    """True when the span is only filled-pause disfluency (um / uh / ah), not yeah/okay."""
    toks = re.findall(r"[A-Za-z0-9']+", text or "")
    if not toks:
        return False
    return all(t.lower() in _FILLED_PAUSE_TOKENS for t in toks)


def opens_with_backchannel_completion(text: str) -> bool:
    """True when later speech starts with Okay/Then completing the prior beat."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    toks = re.findall(r"[A-Za-z0-9']+", stripped)
    if not toks:
        return False
    first = toks[0].lower()
    if first in _BACKCHANNEL_OPEN_TOKENS:
        return True
    return first in {"then", "so"} and len(toks) > 1


def ends_hanging_setup(text: str) -> bool:
    """True when the audible end is a hanging setup / incomplete promise."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    # Ellipsis / unfinished trail always hangs, even if a prior clause had punct.
    if stripped.endswith("...") or stripped.endswith("…"):
        return True
    # STT often puts a period on a fragment ("if I could do through cell biopsy.").
    if last_clause_is_subordinate_fragment(stripped):
        return True
    if stripped[-1] in ".!?":
        return False
    # Trailing comma without terminal close is an unfinished clause.
    if stripped.endswith(","):
        return True
    # Dangling interrogative stubs: "like, do..." / "what if" / "how do"
    if re.search(
        r"(?i)\b(?:do|does|did|is|are|was|were|can|could|would|will|should|"
        r"what|how|why|when|where)\s*$",
        stripped,
    ):
        return True
    if _last_token(stripped) in _INCOMPLETE_TAIL_TOKENS:
        return True
    if ends_unfinished_nominal(stripped):
        return True
    return bool(_HANGING_SETUP_RE.search(stripped))


def ends_unfinished_nominal(text: str) -> bool:
    """Determiner + optional intensifier + adjective-like last token, no terminal close.

    Catches *a very novel* / *a novel*. Does not mark bare evaluative closes
    (*that's novel*, *really powerful*).
    """
    stripped = (text or "").strip()
    if not stripped or stripped[-1:] in ".!?":
        return False
    toks = [t.lower() for t in re.findall(r"[A-Za-z0-9']+", stripped)]
    if len(toks) < 2:
        return False
    last = toks[-1]
    if not _NOMINAL_ADJECTIVE_RE.match(last):
        return False
    idx = len(toks) - 2
    while idx >= 0 and toks[idx] in _INTENSIFIERS:
        idx -= 1
    return idx >= 0 and toks[idx] in _DETERMINERS


def later_opens_nominal_complement(text: str) -> bool:
    """True when later speech opens the missing noun/number complement of a hanging NP."""
    toks = [t.lower() for t in re.findall(r"[A-Za-z0-9']+", text or "")]
    if not toks:
        return False
    first = toks[0]
    if first[:1].isdigit():
        return True
    if first in _NEW_UNIT_OPENERS:
        return False
    if first in _CONTINUER_OPEN_TOKENS:
        return True
    if first in {"i", "you", "we", "they", "he", "she", "it", "okay", "yeah", "yes", "no"}:
        return False
    return True


def ends_complete_thought(
    text: str,
    *,
    next_pause_ms: int | None = None,
    pause_split_ms: int = DEFAULT_PAUSE_SPLIT_MS,
) -> bool:
    """True when text ends on terminal punctuation, or on a non-hanging word
    followed by a pause long enough to read as a finished thought.

    Word choice alone (e.g. any noun/verb close) is no longer sufficient —
    without terminal punctuation we require actual pause evidence
    (``next_pause_ms >= pause_split_ms``) so mid-sentence commas/breaths
    aren't mistaken for a complete thought. Hanging multi-word setups are
    never complete even with a long pause.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    # Ellipsis is never a complete thought, even if listed among unicode dots.
    if stripped.endswith("...") or stripped.endswith("…"):
        return False
    if ends_hanging_setup(stripped):
        return False
    if stripped[-1] in ".!?":
        return True
    return next_pause_ms is not None and next_pause_ms >= pause_split_ms


# Backward-compatible private alias
_ends_complete_thought = ends_complete_thought


def _word_token(w: dict[str, Any]) -> str:
    return str(w.get("text") or w.get("word") or "").strip()


def words_after_end(
    words: list[dict[str, Any]],
    end_ms: int,
    *,
    max_lookahead_ms: int = CLAUSE_CONTINUE_MAX_GAP_MS,
    abut_tol_ms: int = WORD_ABUT_TOL_MS,
) -> list[dict[str, Any]]:
    """Words that begin at or after ``end_ms``, including zero-gap abutting tokens.

    A following word that *starts* at exactly ``end_ms`` (or a few ms earlier due
    to STT overlap) is the next token, not the word that just closed.
    """
    if not words or end_ms < 0:
        return []
    ahead: list[dict[str, Any]] = []
    for w in words:
        if not isinstance(w, dict) or not _word_token(w):
            continue
        try:
            start = int(w.get("start_ms") or 0)
            close = int(w.get("end_ms") or start)
        except (TypeError, ValueError):
            continue
        if close <= end_ms:
            continue
        if start < end_ms - int(abut_tol_ms):
            continue
        if start > end_ms + int(max_lookahead_ms):
            continue
        ahead.append(w)
    ahead.sort(key=lambda w: int(w.get("start_ms") or 0))
    return ahead


def _text_ending_at(words: list[dict[str, Any]], end_ms: int) -> str:
    before = [
        w
        for w in words
        if isinstance(w, dict)
        and int(w.get("end_ms") or 0) <= end_ms + WORD_ABUT_TOL_MS
        and int(w.get("end_ms") or 0) >= end_ms - 12_000
        and _word_token(w)
    ]
    return " ".join(_word_token(w) for w in before[-24:]) if before else ""


def end_is_hanging_clause(words: list[dict[str, Any]], end_ms: int) -> bool:
    """True when the tape at ``end_ms`` is not a listen-complete hinge.

    A trailing ``.!?`` does not legalize a hanging setup (STT often closes
    mid-thought with a period).
    """
    if clause_continues_after(words, end_ms):
        return True
    text = _text_ending_at(words, end_ms)
    return bool(text) and ends_setup_ignoring_terminal_punct(text)


def ends_setup_ignoring_terminal_punct(text: str) -> bool:
    """Hanging-setup check that ignores a trailing ``.!?`` (soft-hang STT closes)."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    core = re.sub(r"[.!?…]+$", "", stripped).strip()
    if not core:
        return False
    return ends_hanging_setup(core) or bool(_HANGING_SETUP_RE.search(core))


def end_is_hard_hang(words: list[dict[str, Any]], end_ms: int) -> bool:
    """True when the audible end is a weak/incomplete tail (Phase 1 hard hang)."""
    text = _text_ending_at(words, end_ms)
    if not text:
        return False
    # Strip terminal punct so "and." still counts as a hard hang.
    core = re.sub(r"[.!?…]+$", "", text.strip()).strip()
    if not core:
        return False
    if _last_token(core) in _INCOMPLETE_TAIL_TOKENS:
        return True
    if ends_hanging_setup(core):
        return True
    return clause_continues_after(words, end_ms)


SAME_ANSWER_MAX_GAP_MS = 3000


def same_answer_continues(
    words: list[dict[str, Any]],
    left_end_ms: int,
    right_start_ms: int | None = None,
    *,
    max_gap_ms: int = SAME_ANSWER_MAX_GAP_MS,
) -> bool:
    """True when speech after ``left_end_ms`` continues the same answer.

    Covers hard hangs (clause continue) and soft hangs (period on a setup whose
    payoff starts within ``max_gap_ms``). Used to refuse hitch splits and
    chapter-hinge air through a still-running answer.
    """
    if not words or left_end_ms < 0:
        return False
    ahead = words_after_end(
        words,
        left_end_ms,
        max_lookahead_ms=max(int(max_gap_ms), CLAUSE_CONTINUE_MAX_GAP_MS),
        abut_tol_ms=WORD_ABUT_TOL_MS,
    )
    if not ahead:
        return False
    first_start = int(ahead[0].get("start_ms") or 0)
    if right_start_ms is not None:
        right = int(right_start_ms)
        if right < left_end_ms:
            return False
        if first_start > right + WORD_ABUT_TOL_MS:
            # Right clip starts later than the immediate continuation — still
            # allow when the first continuing word is inside the gap window.
            pass
    gap = max(0, first_start - int(left_end_ms))
    if gap > int(max_gap_ms):
        return False
    if clause_continues_after(
        words, left_end_ms, max_lookahead_ms=max(int(max_gap_ms), CLAUSE_CONTINUE_MAX_GAP_MS)
    ):
        return True
    left_text = _text_ending_at(words, left_end_ms)
    if left_text and ends_setup_ignoring_terminal_punct(left_text):
        return True
    return False


def speaker_at_ms(words: list[dict[str, Any]], ms: int) -> str:
    """Speaker covering ``ms``, else the last word ending at or before it."""
    if not words:
        return ""
    covering = ""
    last_before = ""
    for w in words:
        if not isinstance(w, dict):
            continue
        try:
            start = int(float(w.get("start_ms") or 0))
            end = int(float(w.get("end_ms") or 0))
        except (TypeError, ValueError):
            continue
        spk = str(w.get("speaker_id") or w.get("speaker") or "").strip()
        if start <= ms <= end and spk:
            covering = spk
        if end <= ms and spk:
            last_before = spk
    return covering or last_before


def same_speaker_continuous_keep(
    left: dict[str, Any],
    right: dict[str, Any],
    words: list[dict[str, Any]] | None = None,
    *,
    max_gap_ms: int = SAME_ANSWER_MAX_GAP_MS,
) -> bool:
    """True when adjacent keepers are the same speaker on continuous tape.

    Includes complete sentence → next sentence (``happening.`` / ``Regulators``).
    Chapter metadata must not split this as a speech cut.
    """
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    try:
        left_end = int(left.get("end_ms") or 0)
        right_start = int(right.get("start_ms") or 0)
    except (TypeError, ValueError):
        return False
    if right_start < left_end:
        return False
    gap = right_start - left_end
    if gap > int(max_gap_ms):
        return False
    left_spk = str(left.get("speaker_id") or left.get("speaker") or "").strip()
    right_spk = str(right.get("speaker_id") or right.get("speaker") or "").strip()
    word_list = words if isinstance(words, list) else []
    if not left_spk and word_list:
        left_spk = speaker_at_ms(word_list, left_end)
    if not right_spk and word_list:
        right_spk = speaker_at_ms(word_list, right_start)
    if not left_spk or not right_spk or left_spk != right_spk:
        return False
    if word_list and same_answer_continues(word_list, left_end, right_start, max_gap_ms=max_gap_ms):
        return True
    return True


def clause_continues_after(
    words: list[dict[str, Any]],
    end_ms: int,
    *,
    max_lookahead_ms: int = CLAUSE_CONTINUE_MAX_GAP_MS,
    pause_split_ms: int = DEFAULT_PAUSE_SPLIT_MS,
) -> bool:
    """True when G0 words after ``end_ms`` continue the same unfinished clause/setup.

    A new conceptual unit (fresh opener after a real pause, or new sentence) does
    **not** count as continuation — that hinge is legal even without ``.!?``.
    """
    if not words or end_ms < 0:
        return False
    ahead = words_after_end(
        words, end_ms, max_lookahead_ms=max_lookahead_ms, abut_tol_ms=WORD_ABUT_TOL_MS
    )
    if not ahead:
        return False
    first = ahead[0]
    gap = max(0, int(first.get("start_ms") or 0) - int(end_ms))
    first_tok = _word_token(first).lower().strip(".,!?;:\"'")
    end_text = _text_ending_at(words, end_ms)
    hanging_close = bool(end_text) and ends_hanging_setup(end_text)
    unfinished_np = bool(end_text) and ends_unfinished_nominal(end_text)
    later_head = " ".join(_word_token(w) for w in ahead[:12])
    last = _last_token(end_text)
    adjective_tail = bool(last) and bool(_NOMINAL_ADJECTIVE_RE.match(last))
    if hanging_close and gap <= CLAUSE_CONTINUE_MAX_GAP_MS:
        if opens_with_backchannel_completion(later_head) or first_tok in _CONTINUER_OPEN_TOKENS:
            return True
        if unfinished_np and later_opens_nominal_complement(later_head):
            return True
    if (
        adjective_tail
        and later_opens_nominal_complement(later_head)
        and gap <= CLAUSE_CONTINUE_MAX_GAP_MS
        and (not end_text or end_text[-1:] not in ".!?")
    ):
        return True
    if gap >= pause_split_ms and not hanging_close:
        # Real pause then new unit — not same-clause continuation.
        return False
    if hanging_close and gap < pause_split_ms:
        return True
    if end_text:
        last_tok = end_text.split()[-1] if end_text.split() else ""
        if last_tok[-1:] in ".!?…" and not hanging_close:
            return False
        if unfinished_np:
            return False
        if ends_hanging_setup(end_text):
            return True
        if last in _INCOMPLETE_TAIL_TOKENS:
            return True
    # Tight gap + content continuation of the same clause.
    if first_tok in _NEW_UNIT_OPENERS and gap >= 350 and not hanging_close:
        return False
    # Look at a few upcoming tokens — lowercase continuers are same-clause.
    cont = " ".join(_word_token(w) for w in ahead[:8]).lower()
    if re.match(
        r"^(you|we|i|they|he|she|it|to|that|which|who|how|what|when|where|"
        r"and|or|but|because|if|of|for|with|into|onto|from)\b",
        cont,
    ):
        return True
    # No terminal punct behind and tight gap → treat as unfinished.
    return gap < 450


def is_legal_conceptual_hinge(
    text: str,
    *,
    words: list[dict[str, Any]] | None = None,
    end_ms: int | None = None,
    next_pause_ms: int | None = None,
    pause_split_ms: int = DEFAULT_PAUSE_SPLIT_MS,
) -> bool:
    """Shared predicate: word-aligned listen-complete idea boundary (not hang).

    Full grammatical sentences are one legal hinge type — not the only one.
    When ``words`` + ``end_ms`` are provided, also rejects cuts where the next
    transcript words continue the same unfinished setup.
    """
    complete = ends_complete_thought(
        text, next_pause_ms=next_pause_ms, pause_split_ms=pause_split_ms
    )
    if not complete:
        # Conceptual hinge without terminal punct / measured pause: allow when
        # lookahead shows a *new* unit (not same-clause continue) and text is
        # not a hanging setup.
        stripped = (text or "").strip()
        if not stripped or ends_hanging_setup(stripped):
            return False
        if words is not None and end_ms is not None:
            if clause_continues_after(
                words, end_ms, pause_split_ms=pause_split_ms
            ):
                return False
            ahead = words_after_end(words, end_ms)
            if ahead:
                pause = next_pause_ms
                if pause is None:
                    pause = max(
                        0, int(ahead[0].get("start_ms") or 0) - int(end_ms)
                    )
                # Abutting / mid-breath next token without a new unit is not a hinge.
                if pause < ZERO_GAP_HINGE_MS:
                    return False
            # Non-hanging content word with no same-clause continue = legal hinge.
            return True
        return False
    if words is not None and end_ms is not None:
        if clause_continues_after(words, end_ms, pause_split_ms=pause_split_ms):
            return False
    return True


def _normalize_tok(tok: str) -> str:
    return (tok or "").lower().strip(".,!?;:\"'()[]")


def opens_with_clause_continuer(text: str) -> bool:
    """True when spoken text starts mid-clause (and/but/because/which/...)."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    first = _normalize_tok(stripped.split(None, 1)[0])
    return first in _CONTINUER_OPEN_TOKENS


def clause_continues_before(
    words: list[dict[str, Any]],
    start_ms: int,
    *,
    max_lookback_ms: int = 4000,
    pause_split_ms: int = DEFAULT_PAUSE_SPLIT_MS,
) -> bool:
    """True when G0 words immediately before ``start_ms`` leave the open mid-clause/list.

    Catches late opens that drop the first list item or start on a continuer
    ("Naturell…" after "Amazon,", "and yet…" as a false start of a new window).
    """
    if not words or start_ms <= 0:
        return False
    ahead = [
        w
        for w in words
        if isinstance(w, dict)
        and start_ms <= int(w.get("start_ms") or 0) <= start_ms + max_lookback_ms
        and _word_token(w)
    ]
    ahead.sort(key=lambda w: int(w.get("start_ms") or 0))
    first_tok = _normalize_tok(_word_token(ahead[0])) if ahead else ""
    before = [
        w
        for w in words
        if isinstance(w, dict)
        and start_ms - max_lookback_ms <= int(w.get("end_ms") or 0) <= start_ms
        and _word_token(w)
    ]
    if not before:
        return first_tok in _CONTINUER_OPEN_TOKENS
    before.sort(key=lambda w: int(w.get("end_ms") or 0))
    last = before[-1]
    last_tok_raw = _word_token(last)
    last_tok = _normalize_tok(last_tok_raw)
    gap = int(start_ms) - int(last.get("end_ms") or 0)
    if gap >= pause_split_ms:
        return False
    if last_tok_raw[-1:] in ".!?…":
        return False
    prev_text = " ".join(_word_token(w) for w in before[-16:])
    if ends_hanging_setup(prev_text) or last_tok in _INCOMPLETE_TAIL_TOKENS:
        return True
    if last_tok_raw.rstrip().endswith(","):
        return True
    if first_tok in _CONTINUER_OPEN_TOKENS and gap < pause_split_ms:
        return True
    # Tight gap after a non-terminal word → likely mid-phrase open.
    return gap < 450 and last_tok not in _NEW_UNIT_OPENERS


def is_legal_conceptual_open(
    text: str,
    *,
    words: list[dict[str, Any]] | None = None,
    start_ms: int | None = None,
    prev_pause_ms: int | None = None,
    pause_split_ms: int = DEFAULT_PAUSE_SPLIT_MS,
) -> bool:
    """True when a cut *start* begins a listen-complete idea (not mid-list/clause)."""
    stripped = (text or "").strip()
    first = _normalize_tok(stripped.split()[0]) if stripped else ""
    if first in _CONTINUER_OPEN_TOKENS:
        # Continuer opens are legal only after a real pause (new unit).
        if prev_pause_ms is not None and prev_pause_ms >= pause_split_ms:
            return True
        if words is not None and start_ms is not None:
            return not clause_continues_before(
                words, start_ms, pause_split_ms=pause_split_ms
            )
        return False
    if words is not None and start_ms is not None:
        if clause_continues_before(words, start_ms, pause_split_ms=pause_split_ms):
            return False
    if prev_pause_ms is not None and prev_pause_ms >= pause_split_ms:
        return True
    return True


def is_micro_segment(seg: dict[str, Any] | None, *, cfg: dict[str, Any]) -> bool:
    if not isinstance(seg, dict):
        return False
    text = str(seg.get("text") or "").strip()
    words = _word_count(text)
    dur = max(0, int(seg.get("end_ms") or 0) - int(seg.get("start_ms") or 0))
    if words <= int(cfg.get("micro_max_words") or 4):
        return True
    if dur > 0 and dur < int(cfg.get("micro_max_ms") or 2000) and words <= 8:
        return True
    return False


_is_micro_segment = is_micro_segment


def looks_like_impact_beat(
    seg: dict[str, Any] | None,
    *,
    cfg: dict[str, Any],
    next_pause_ms: int | None = None,
) -> bool:
    if not isinstance(seg, dict):
        return False
    text = str(seg.get("text") or "").strip()
    if not text or not _ends_complete_thought(text, next_pause_ms=next_pause_ms):
        return False
    words = _word_count(text)
    dur = max(0, int(seg.get("end_ms") or 0) - int(seg.get("start_ms") or 0))
    if words < int(cfg.get("impact_min_words") or 18):
        return False
    if dur > 0 and dur < int(cfg.get("impact_min_duration_ms") or 8000):
        # Short but punchy complete close can still be impactful.
        if not _MIC_DROP_HINT_RE.search(text):
            return False
    if _MIC_DROP_HINT_RE.search(text):
        return True
    # Complete guest answer of decent length with a strong closing sentence.
    last_sentence = re.split(r"[.!?]", text)[-1] if "." in text or "!" in text or "?" in text else text
    if _word_count(last_sentence) >= 8 and words >= int(cfg.get("impact_min_words") or 18):
        return True
    return False


_looks_like_impact_beat = looks_like_impact_beat


def _chapter_title_for(segment_id: str, chapters: list[dict[str, Any]] | None) -> str | None:
    if not chapters:
        return None
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        ids = [str(s) for s in (ch.get("segment_ids") or [])]
        if segment_id in ids:
            title = str(ch.get("title") or ch.get("name") or "").strip()
            return title or None
    return None


def _end_window(text: str, *, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[-max_chars:].lstrip()


def _quote_span(text: str, *, max_chars: int = 180) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    # Prefer last sentence.
    parts = re.split(r"(?<=[.!?])\s+", t)
    last = (parts[-1] if parts else t).strip()
    if len(last) > max_chars:
        return last[-max_chars:].lstrip()
    return last


def _next_segment_pause_ms(
    seg_id: str,
    *,
    ordered_ids: list[str],
    segments_by_id: dict[str, dict[str, Any]],
) -> int | None:
    """Gap in ms between ``seg_id``'s end and the next ordered segment's start."""
    if seg_id not in ordered_ids:
        return None
    idx = ordered_ids.index(seg_id)
    if idx + 1 >= len(ordered_ids):
        return None
    seg = segments_by_id.get(seg_id)
    nxt = segments_by_id.get(ordered_ids[idx + 1])
    if not isinstance(seg, dict) or not isinstance(nxt, dict):
        return None
    try:
        gap = int(nxt.get("start_ms") or 0) - int(seg.get("end_ms") or 0)
    except (TypeError, ValueError):
        return None
    return max(0, gap)


def build_prior_native_context(
    *,
    target_segment_id: str,
    ordered_ids: list[str],
    segments_by_id: dict[str, dict[str, Any]],
    chapters: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build prior_native_context packet for VO targeting ``target_segment_id``.

    Walks backward past micro/backchannel segments so a VO before a real answer
    still sees the last substantive native beat (e.g. skip \"Okay.\" to the mic-drop).
    """
    settings = cfg or prior_context_cfg()
    if not settings.get("enabled", True):
        return None
    tid = str(target_segment_id or "").strip()
    if not tid or tid not in ordered_ids:
        return None
    idx = ordered_ids.index(tid)
    if idx <= 0:
        return None
    prior_id = None
    for cand in reversed(ordered_ids[:idx]):
        if _is_micro_segment(segments_by_id.get(cand), cfg=settings):
            continue
        prior_id = cand
        break
    if prior_id is None:
        # Only micros behind — still expose the immediate neighbor.
        prior_id = ordered_ids[idx - 1]
    prior = segments_by_id.get(prior_id)
    if not isinstance(prior, dict):
        return None
    text = str(prior.get("text") or "").strip()
    full_max = int(settings.get("full_text_max_chars") or 900)
    end_max = int(settings.get("end_window_chars") or 420)
    next_pause_ms = _next_segment_pause_ms(
        prior_id, ordered_ids=ordered_ids, segments_by_id=segments_by_id
    )
    complete = _ends_complete_thought(text, next_pause_ms=next_pause_ms)
    impact = _looks_like_impact_beat(prior, cfg=settings, next_pause_ms=next_pause_ms)
    return {
        "segment_id": prior_id,
        "speaker_role": str(prior.get("speaker_role") or prior.get("type") or "") or None,
        "speaker_id": str(prior.get("speaker_id") or "") or None,
        "text": text[:full_max] if text else "",
        "end_window_text": _end_window(text, max_chars=end_max),
        "start_ms": int(prior.get("start_ms") or 0),
        "end_ms": int(prior.get("end_ms") or 0),
        "chapter_title": _chapter_title_for(prior_id, chapters),
        "prior_impact_beat": bool(impact),
        "prior_complete_thought": bool(complete),
        "quote_span": _quote_span(text) if impact or complete else _quote_span(text, max_chars=120),
        "target_segment_id": tid,
        "target_is_micro": _is_micro_segment(segments_by_id.get(tid), cfg=settings),
    }


def next_substantive_target(
    *,
    preferred_id: str,
    ordered_ids: list[str],
    segments_by_id: dict[str, dict[str, Any]],
    cfg: dict[str, Any] | None = None,
) -> str:
    """If preferred target is a micro/backchannel, relocate to the next substantive segment."""
    settings = cfg or prior_context_cfg()
    if not settings.get("relocate_micro_targets", True):
        return preferred_id
    tid = str(preferred_id or "").strip()
    if not tid or tid not in ordered_ids:
        return preferred_id
    if not _is_micro_segment(segments_by_id.get(tid), cfg=settings):
        return tid
    idx = ordered_ids.index(tid)
    for sid in ordered_ids[idx + 1 :]:
        if not _is_micro_segment(segments_by_id.get(sid), cfg=settings):
            return sid
    # Fall back to previous substantive if nothing after.
    for sid in reversed(ordered_ids[:idx]):
        if not _is_micro_segment(segments_by_id.get(sid), cfg=settings):
            return sid
    return tid


def load_ordered_and_segments(ctx: RunContext) -> tuple[list[str], dict[str, dict[str, Any]], list[dict[str, Any]] | None]:
    ordered: list[str] = []
    chapters: list[dict[str, Any]] | None = None
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            ordered = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
            ch = sel.get("chapters")
            if isinstance(ch, list):
                chapters = [c for c in ch if isinstance(c, dict)]
    if not chapters and ctx.artifact_exists("master/narrative_plan.json"):
        plan = ctx.read_json("master/narrative_plan.json")
        if isinstance(plan, dict) and isinstance(plan.get("chapters"), list):
            chapters = [c for c in plan["chapters"] if isinstance(c, dict)]
    by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        for row in (man.get("segments") or []) if isinstance(man, dict) else []:
            if isinstance(row, dict) and row.get("segment_id"):
                by_id[str(row["segment_id"])] = row
    if not ordered:
        ordered = list(by_id.keys())
    return ordered, by_id, chapters


def build_prior_native_contexts_map(ctx: RunContext) -> dict[str, dict[str, Any]]:
    """Map target_segment_id → prior_native_context for every ordered segment after the first."""
    settings = prior_context_cfg()
    if not settings.get("enabled", True):
        return {}
    ordered, by_id, chapters = load_ordered_and_segments(ctx)
    out: dict[str, dict[str, Any]] = {}
    for tid in ordered:
        pkt = build_prior_native_context(
            target_segment_id=tid,
            ordered_ids=ordered,
            segments_by_id=by_id,
            chapters=chapters,
            cfg=settings,
        )
        if pkt:
            out[tid] = pkt
    return out


def attach_prior_native_contexts_to_payload(ctx: RunContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Attach prior_native_contexts (+ courtesy policy) onto a gap framing stage input."""
    settings = prior_context_cfg()
    if not settings.get("enabled", True):
        return payload
    contexts = build_prior_native_contexts_map(ctx)
    payload["prior_native_contexts"] = contexts
    payload["prior_native_context_policy"] = {
        "require_prior_context": True,
        "forbid_interruptive_openers_after_impact": True,
        "forbidden_openers": [
            "Let me pause you there",
            "Hold on",
            "Stop right there",
            "Wait",
            "Hang on",
        ],
        "prefer_acknowledge_or_soft_bridge_after_impact": True,
        "relocate_micro_targets": bool(settings.get("relocate_micro_targets", True)),
        "notes": (
            "For each interviewer line targeting segment S, use prior_native_contexts[S] "
            "(immediate prior ordered native segment). After prior_impact_beat or a complete "
            "strong close, write courteous follow-through only — never interruptive stock."
        ),
    }
    # Compact highlight list for volley conditioning (impact beats first).
    highlights: list[dict[str, Any]] = []
    for tid, pkt in contexts.items():
        if not pkt.get("prior_impact_beat") and not pkt.get("prior_complete_thought"):
            continue
        highlights.append(
            {
                "before_target": tid,
                "prior_segment_id": pkt.get("segment_id"),
                "prior_impact_beat": pkt.get("prior_impact_beat"),
                "prior_complete_thought": pkt.get("prior_complete_thought"),
                "quote_span": pkt.get("quote_span"),
                "chapter_title": pkt.get("chapter_title"),
                "target_is_micro": pkt.get("target_is_micro"),
            }
        )
    if highlights:
        payload["prior_impact_highlights"] = highlights[:40]
    return payload


def build_target_native_context(
    *,
    target_segment_id: str,
    segments_by_id: dict[str, dict[str, Any]],
    chapters: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Upcoming native clip packet so VO can unlock it without restating it."""
    settings = cfg or prior_context_cfg()
    tid = str(target_segment_id or "").strip()
    seg = segments_by_id.get(tid)
    if not tid or not isinstance(seg, dict):
        return None
    text = str(seg.get("text") or seg.get("text_excerpt") or "").strip()
    full_max = int(settings.get("full_text_max_chars") or 900)
    return {
        "segment_id": tid,
        "speaker_role": str(seg.get("speaker_role") or seg.get("type") or "") or None,
        "speaker_id": str(seg.get("speaker_id") or "") or None,
        "type": seg.get("type"),
        "text": text[:full_max] if text else "",
        "start_ms": int(seg.get("start_ms") or 0),
        "end_ms": int(seg.get("end_ms") or 0),
        "chapter_title": _chapter_title_for(tid, chapters),
        "quote_span": _quote_span(text, max_chars=160),
    }


def build_target_native_contexts_map(
    ctx: RunContext,
    *,
    segment_ids: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    settings = prior_context_cfg()
    ordered, by_id, chapters = load_ordered_and_segments(ctx)
    ids = list(segment_ids) if segment_ids is not None else list(ordered)
    out: dict[str, dict[str, Any]] = {}
    for tid in ids:
        pkt = build_target_native_context(
            target_segment_id=str(tid),
            segments_by_id=by_id,
            chapters=chapters,
            cfg=settings,
        )
        if pkt:
            out[str(tid)] = pkt
    return out


def build_vo_missions_map(
    ctx: RunContext,
    *,
    segment_ids: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-target mission: what the synthetic line must accomplish before the clip."""
    evals_by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("understanding/gap_evaluations.json"):
        doc = ctx.read_json("understanding/gap_evaluations.json")
        if isinstance(doc, dict):
            for row in doc.get("evaluations") or []:
                if isinstance(row, dict) and row.get("segment_id"):
                    evals_by_id[str(row["segment_id"])] = row

    tp_titles: list[str] = []
    if ctx.artifact_exists("understanding/talking_points.json"):
        tp = ctx.read_json("understanding/talking_points.json")
        if isinstance(tp, dict):
            for row in tp.get("talking_points") or []:
                if isinstance(row, dict) and row.get("title"):
                    tp_titles.append(str(row["title"]))

    ordered, _, _ = load_ordered_and_segments(ctx)
    ids = list(segment_ids) if segment_ids is not None else list(ordered)
    out: dict[str, dict[str, Any]] = {}
    for tid in ids:
        sid = str(tid)
        ev = evals_by_id.get(sid) or {}
        confusion = str(ev.get("listener_confusion") or "").strip()
        gap_type = str(ev.get("gap_type") or "").strip()
        recommended = str(ev.get("recommended_framing") or "").strip()
        mission = recommended or confusion
        if not mission:
            if gap_type and gap_type not in ("ok_with_light_bridge", "none", "ok"):
                mission = f"Orient the listener for gap_type={gap_type} before the next native beat."
            else:
                mission = "Add conversational value that unlocks the next native clip without restating it."
        out[sid] = {
            "segment_id": sid,
            "gap_type": gap_type or None,
            "severity": ev.get("severity"),
            "listener_confusion": confusion or None,
            "recommended_framing": recommended or None,
            "mission": mission,
            "related_talking_point_titles": tp_titles[:8] if tp_titles else [],
        }
    return out


def attach_vo_partner_context_to_payload(
    ctx: RunContext,
    payload: dict[str, Any],
    *,
    segment_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Attach target clip text + VO missions so compose can act as a conversation partner."""
    targets = build_target_native_contexts_map(ctx, segment_ids=segment_ids)
    missions = build_vo_missions_map(ctx, segment_ids=segment_ids)
    if targets:
        payload["target_native_contexts"] = targets
    if missions:
        payload["vo_missions"] = missions
    payload["vo_partner_policy"] = {
        "must_add_conversational_value": True,
        "never_restate_next_clip": True,
        "require_rationale": True,
        "allowed_pov": ["host_first_person", "host_second_person", "expository_third_person"],
        "notes": (
            "Each synthetic line is a conversation-partner turn: unlock stakes, ask a real "
            "follow-up, define assumed knowledge, or bridge topics. Use target_native_contexts[S] "
            "to know what the next clip already says — do not paraphrase it. Honor vo_missions[S]."
        ),
    }
    if "talking_points" not in payload and ctx.artifact_exists("understanding/talking_points.json"):
        tp = ctx.read_json("understanding/talking_points.json")
        if isinstance(tp, dict):
            payload["talking_points"] = {
                "strategy_summary": tp.get("strategy_summary"),
                "through_line": tp.get("through_line"),
                "talking_points": [
                    {
                        "talking_point_id": row.get("talking_point_id"),
                        "title": row.get("title"),
                        "importance": row.get("importance"),
                        "why_it_matters": row.get("why_it_matters"),
                    }
                    for row in (tp.get("talking_points") or [])
                    if isinstance(row, dict)
                ][:40],
            }
    return payload


def vo_value_gate_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = ((cfg or merged_config()).get("analysis") or {}).get("gap_framing") or {}
    block = raw.get("vo_value_gate") if isinstance(raw.get("vo_value_gate"), dict) else {}
    defaults = {
        "enabled": True,
        "require_rationale": True,
        "restate_overlap_max": 0.75,
        "restate_min_vo_tokens": 6,
        "allow_summary_overlap_max": 0.75,
        "enforce_courtesy": True,
        "require_forward_cue": True,
        "require_cold_open_layup": True,
    }
    return {**defaults, **block}


def _tokenize_for_overlap(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def vo_target_overlap_ratio(vo_text: str, target_text: str) -> float:
    """Fraction of VO tokens that also appear in the target clip (content-word overlap)."""
    vo_toks = _tokenize_for_overlap(vo_text)
    tgt_toks = set(_tokenize_for_overlap(target_text))
    if len(vo_toks) < 1 or not tgt_toks:
        return 0.0
    # Drop ultra-common stopwords from VO side so short bridges aren't false-positives.
    stop = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "to",
        "of",
        "in",
        "on",
        "for",
        "is",
        "are",
        "was",
        "were",
        "that",
        "this",
        "it",
        "you",
        "we",
        "i",
        "he",
        "she",
        "they",
        "what",
        "how",
        "why",
        "when",
        "with",
        "as",
        "at",
        "be",
        "so",
        "if",
        "from",
        "about",
        "just",
        "like",
        "here",
        "next",
        "now",
    }
    content = [t for t in vo_toks if t not in stop]
    if not content:
        return 0.0
    hits = sum(1 for t in content if t in tgt_toks)
    return hits / len(content)


_FORWARD_CUE_RE = re.compile(
    r"(?:"
    r"\?|"
    r"\b(?:what|how|why|where|when|who)\b|"
    r"\b(?:tell me|walk me|take us|take me|help us|help me)\b|"
    r"\b(?:coming up|next|follow|follows|sets? up|opens?|leads?)\b|"
    r"\b(?:shall we|let's|lets)\b"
    r")",
    re.IGNORECASE,
)

_GENERIC_ORIGIN_RE = re.compile(
    r"\b(?:origin|spark|how (?:it|this) (?:all )?started|where (?:it|this) began|"
    r"founding story|how did you (?:get|start))\b",
    re.IGNORECASE,
)
_GENERIC_HANDOFF_RE = re.compile(
    r"\b(?:let['’]?s hear how it unfolded|let['’]?s hear the story|"
    r"now let['’]?s hear|let['’]?s get into it)\b",
    re.IGNORECASE,
)
# Abstract quiz closers sound like planner prompts, not podcast cold opens
# (exec_017: "What does the conventional route ask of a patient?").
_WEAK_QUIZ_PREFACE_RE = re.compile(
    r"\bwhat does (?:the|that|this|a|an)\b.+\b"
    r"(?:ask|reveal|mean|tell|require|demand|suggest|imply)\b",
    re.IGNORECASE,
)


def last_spoken_sentence(text: str) -> str:
    """Return the last sentence-like span of spoken VO."""
    stripped = str(text or "").strip()
    if not stripped:
        return ""
    parts = re.split(r"(?<=[.!?…])\s+", stripped)
    parts = [p.strip() for p in parts if p.strip()]
    return parts[-1] if parts else stripped


def last_sentence_restates_target(
    text: str,
    target_text: str,
    *,
    overlap_max: float | None = None,
) -> bool:
    """True when the last spoken sentence restates the next clip above the ceiling."""
    last = last_spoken_sentence(text)
    tgt = str(target_text or "").strip()
    if not last or not tgt:
        return False
    settings = vo_value_gate_cfg()
    limit = float(
        overlap_max
        if overlap_max is not None
        else (
            settings.get("restate_overlap_max")
            or settings.get("allow_summary_overlap_max")
            or 0.75
        )
    )
    return vo_target_overlap_ratio(last, tgt) > (limit + 1e-6)


def has_forward_cue(text: str) -> bool:
    last = last_spoken_sentence(text)
    if not last:
        return False
    return bool(_FORWARD_CUE_RE.search(last))


def cold_open_layup_ok(
    line: dict[str, Any],
    *,
    target_text: str,
    ordered_ids: list[str] | None = None,
) -> bool:
    """Preface / first-segment last sentence must cue the actual first native, not a generic origin prompt."""
    category = str(line.get("line_category") or "").strip().lower()
    tid = str(line.get("targets_segment_id") or line.get("segment_id") or "").strip()
    ordered = [str(s) for s in (ordered_ids or []) if s]
    is_first = bool(tid and ordered and tid == ordered[0]) or category == "episode_preface"
    if not is_first:
        return True
    last = last_spoken_sentence(str(line.get("text") or ""))
    if not last:
        return False
    if not has_forward_cue(last):
        return False
    if _GENERIC_HANDOFF_RE.search(last):
        return False
    # Preface quiz closers fail the cold-open bar even when they "cue" a topic.
    if category == "episode_preface" and _WEAK_QUIZ_PREFACE_RE.search(last):
        return False
    tgt = str(target_text or "").strip()
    if not tgt:
        return True
    if vo_target_overlap_ratio(last, tgt) > 0.42:
        return False
    # Generic origin/spark prompt when the first clip is about something else (e.g. M&A).
    if _GENERIC_ORIGIN_RE.search(last) and not _GENERIC_ORIGIN_RE.search(tgt):
        return False
    return True


def _target_aware_forward_cues(target_text: str, *, category: str) -> list[str]:
    """Grounded last-sentence candidates that survive spoken_copy + cold-open checks."""
    tgt_l = str(target_text or "").lower()
    cues: list[str] = []
    preface = category == "episode_preface"
    if "contrast" in tgt_l or "versus" in tgt_l or "vs." in tgt_l:
        if preface:
            cues.append("That contrast is where the conversation opens.")
        else:
            cues.append("What does that contrast reveal?")
    if any(tok in tgt_l for tok in ("m&a", "acquisition", "merger", "exit", "deal", "crore", "rupee")):
        if preface:
            cues.append(
                "Let's open on what made that deal possible."
                if "deal" in tgt_l or "m&a" in tgt_l or "acquisition" in tgt_l or "merger" in tgt_l
                else "Let's open on what was at stake in that exit."
            )
        else:
            cues.append(
                "What made that deal possible?"
                if "deal" in tgt_l or "m&a" in tgt_l or "acquisition" in tgt_l or "merger" in tgt_l
                else "What was at stake in that exit?"
            )
    if any(
        tok in tgt_l
        for tok in (
            "who is",
            "who are",
            "on the show",
            "we've got",
            "we have",
            "introduce",
            "introduction",
            "co-founder",
            "ceo",
            "founder",
        )
    ):
        if preface:
            cues.extend(
                [
                    "Let's start with that introduction.",
                    "That introduction is where we begin.",
                ]
            )
        else:
            cues.extend(
                [
                    "Who is at the center — and why start there?",
                    "Why open by establishing that introduction?",
                    "What should we know before that introduction lands?",
                ]
            )
    if preface:
        # Declarative / invitation hinges first — quiz closers are fail-closed above.
        cues.extend(
            [
                "That opening sets the stakes we'll follow.",
                "Let's hear how that opening beat lands.",
                "Let's start with how that story begins.",
            ]
        )
    else:
        cues.extend(
            [
                "What changed next in that stretch?",
                "How does that set up what follows?",
            ]
        )
    # Preserve order while dropping empties/dupes.
    seen: set[str] = set()
    out: list[str] = []
    for cue in cues:
        key = cue.lower()
        if not cue or key in seen:
            continue
        seen.add(key)
        out.append(cue)
    return out


def repair_last_sentence_layup(
    text: str,
    *,
    prior: dict[str, Any] | None = None,
    target_text: str = "",
    category: str = "framing_question",
    target_segment_id: str | None = None,
    max_words: int | None = None,
) -> str:
    """Rewrite only the last sentence into a unique forward unlock from prior+target context.

    When ``max_words`` is set, keep body+cue within that budget (exec_13159: trim then
    blind cue append re-bloomed past context_setup max 20 → post-commit fail).
    """
    stripped = str(text or "").strip()
    parts = re.split(r"(?<=[.!?…])\s+", stripped) if stripped else []
    parts = [p.strip() for p in parts if p.strip()]
    body = " ".join(parts[:-1]) if len(parts) > 1 else ""

    from interview_mux.spoken_copy_guard import shorten_spoken_text, spoken_copy_violations

    def _word_n(s: str) -> int:
        return len(re.findall(r"\S+", s or ""))

    def _fit(body_text: str, cue: str) -> str:
        cue = " ".join(str(cue or "").split()).strip()
        if not cue:
            return " ".join(str(body_text or "").split()).strip()
        if max_words is None or max_words <= 0:
            return f"{body_text} {cue}".strip() if body_text else cue
        cue_n = _word_n(cue)
        if cue_n >= max_words:
            # Cue alone fills the budget — prefer the cue (forward-cue lint wins).
            words = re.findall(r"\S+", cue)[:max_words]
            return " ".join(words)
        room = max_words - cue_n
        body_clean = " ".join(str(body_text or "").split()).strip()
        if not body_clean:
            return cue
        if _word_n(body_clean) > room:
            body_clean = shorten_spoken_text(body_clean, room)
        if not body_clean or _word_n(body_clean) > room:
            return cue
        out = f"{body_clean} {cue}".strip()
        if _word_n(out) > max_words:
            return cue
        return out

    # Prefer target-grounded hinges before the generic courtesy seed so a
    # contrast/intro clip does not get a weaker stock cue first.
    candidates = list(_target_aware_forward_cues(target_text, category=category))
    seeded = courtesy_seed_text(prior, category=category, target_segment_id=target_segment_id)
    if seeded:
        candidates.append(seeded)

    evidence = {
        "target_excerpt": str(target_text or ""),
        "before_excerpt": str((prior or {}).get("quote_span") or "") if isinstance(prior, dict) else "",
        "strict_grounding": False,
    }
    for cue in candidates:
        cue = " ".join(str(cue or "").split()).strip()
        if not cue:
            continue
        if spoken_copy_violations(cue, evidence=evidence, seen_texts=[]):
            continue
        candidate = _fit(body, cue)
        if not body and cue.endswith("?"):
            # A question with no factual body is not a layup/orientation.
            continue
        if not candidate:
            continue
        probe = {
            "text": candidate,
            "line_category": category,
            "targets_segment_id": str(target_segment_id or ""),
        }
        if category == "episode_preface" and not cold_open_layup_ok(
            probe, target_text=target_text, ordered_ids=[str(target_segment_id or "")]
        ):
            continue
        return candidate

    # Last resort: always attach a speakable forward cue. A single factual
    # sentence with no body split used to return unchanged (exec_11630
    # vo_bridge_seg_044 → post-commit "needs a forward cue" loop).
    fallback = "Let's hear how that beat lands."
    if body:
        return _fit(body, fallback)
    if stripped and not stripped.endswith("?"):
        base = stripped.rstrip(".!?…").rstrip()
        return _fit(f"{base}.", fallback) if base else fallback
    if stripped.endswith("?"):
        if max_words is not None and max_words > 0 and _word_n(stripped) > max_words:
            return _fit("", stripped)  # question alone; _fit truncates if needed
        return stripped
    return fallback or seeded or stripped


def vo_value_violations(
    lines: list[dict[str, Any]],
    *,
    segments_by_id: dict[str, dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
    ordered_ids: list[str] | None = None,
) -> list[str]:
    """Deterministic VO partner quality: rationale + no-restate + courtesy + layup."""
    settings = vo_value_gate_cfg(cfg)
    if not settings.get("enabled", True):
        return []
    errs: list[str] = []
    segs = segments_by_id or {}
    # Single soft ceiling for all line categories — intentional setup/repetition
    # is allowed; only near-verbatim restatement fails.
    overlap_max = float(
        settings.get("restate_overlap_max")
        or settings.get("allow_summary_overlap_max")
        or 0.75
    )
    min_toks = int(settings.get("restate_min_vo_tokens") or 6)

    if settings.get("enforce_courtesy", True):
        errs.extend(courtesy_violations(lines))

    for line in lines:
        if not isinstance(line, dict):
            continue
        if line.get("skipped_optional"):
            continue
        lid = str(line.get("line_id") or line.get("targets_segment_id") or "?")
        text = str(line.get("text") or "").strip()
        if settings.get("require_rationale", True):
            rationale = str(line.get("rationale") or "").strip()
            if text and not rationale:
                errs.append(f"{lid}: missing rationale (conversation-partner value)")
        tid = str(line.get("targets_segment_id") or line.get("segment_id") or "").strip()
        if not text:
            continue
        if settings.get("require_forward_cue", True) and not has_forward_cue(text):
            errs.append(f"{lid}: last sentence needs a forward cue into the next beat")
        target = segs.get(tid) or {}
        target_text = str(target.get("text") or target.get("text_excerpt") or "")
        if settings.get("require_cold_open_layup", True) and not cold_open_layup_ok(
            line, target_text=target_text, ordered_ids=ordered_ids
        ):
            errs.append(
                f"{lid}: cold-open / preface last sentence must cue the first native clip "
                "without restating it or using a generic origin prompt"
            )
        if not tid or not target_text:
            continue
        vo_toks = _tokenize_for_overlap(text)
        if len(vo_toks) < min_toks:
            continue
        ratio = vo_target_overlap_ratio(text, target_text)
        category = str(line.get("line_category") or "").strip().lower()
        limit = overlap_max
        # Use a tiny epsilon so float noise at the configured ceiling
        # (e.g. 0.75000001 vs 0.75) does not hard-fail post-commit.
        if ratio > (limit + 1e-6):
            errs.append(
                f"{lid}: VO restates next clip (overlap={ratio:.2f} > {limit:.2f} for {category or 'line'})"
            )
        last = last_spoken_sentence(text)
        if last and vo_target_overlap_ratio(last, target_text) > (limit + 1e-6):
            errs.append(
                f"{lid}: last sentence restates next clip (overlap too high)"
            )
    return errs


def is_interruptive_opener(text: str) -> bool:
    return bool(INTERRUPTIVE_OPENER_RE.match(text or ""))


# Diversified stock lines so multi-seed high-gap repair does not collapse into
# identical copy that spoken_copy_guard omits as spoken_repeated_copy (exec_13157).
# Keep only phrases that pass spoken_copy_guard + spoken_meta_lint (no segment/clip).
# ISSUES 123: three former entries ("What tension carries into what comes
# next?", "How should we hear what follows differently?", "How does that
# landing set up what follows?") trip the guard's generic-filler ban; a seed
# minted with one of them could never be spoken, and the run died on it
# (maintainer's exec_010). A test keeps this pool and the guard in agreement.
_COURTESY_SEED_POOL: tuple[str, ...] = (
    "How does this next moment reframe what we just heard?",
    "What claim should we test as this continues?",
    "What is at stake as this continues?",
    "What should we listen for as this continues?",
    "What changes if we stay with this idea a beat longer?",
)


def courtesy_seed_text(
    prior: dict[str, Any] | None,
    *,
    category: str,
    target_segment_id: str | None = None,
) -> str:
    """Deterministic courteous density-seed copy with no spoken edit metadata.

    ``target_segment_id`` remains an anchoring input for callers, but is never
    interpolated into listener-facing copy. Always returns non-empty speakable
    text — empty courtesy seeds were omitted then left high gaps lint-dirty.
    """
    quote = ""
    impact = False
    complete = False
    if isinstance(prior, dict):
        quote = str(prior.get("quote_span") or prior.get("end_window_text") or "").strip()
        impact = bool(prior.get("prior_impact_beat"))
        complete = bool(prior.get("prior_complete_thought"))
    # Truncate quote for spoken VO length.
    if len(quote) > 110:
        quote = quote[:107].rstrip() + "…"
    pool_i = (
        zlib.crc32(str(target_segment_id or category).encode("utf-8"))
        % len(_COURTESY_SEED_POOL)
    )
    diversified = _COURTESY_SEED_POOL[pool_i]
    if category == "episode_preface":
        if impact and quote:
            candidate = "That landing stays with you — what should we listen for next?"
        else:
            # Avoid show-scaffold phrases that spoken_copy_guard omits entirely
            # ("Coming up — where does this stretch lead?"), which left orientation
            # with no forward cue and failed cold_open_layup_ok.
            candidate = "Let's hear how that opening beat lands."
    elif category == "segment_summary":
        if quote:
            candidate = "Keep that beat in mind — what claim follows?"
        else:
            candidate = "Here's the hinge — what should we listen for next?"
    elif category == "story_bridge":
        if impact and quote:
            candidate = "That's a sharp point — how does it set up what comes next?"
        elif complete and quote:
            candidate = "That lands — what follows?"
        else:
            candidate = diversified
    elif impact and quote:
        candidate = "Given what you just said — how did that reshape what came next?"
    elif complete and quote:
        candidate = "Building on that — what changed next?"
    else:
        candidate = diversified

    from interview_mux.spoken_copy_guard import guard_spoken_copy

    evidence = {
        "before_excerpt": quote,
        "source_gap_ms": prior.get("source_gap_ms")
        if isinstance(prior, dict)
        else None,
    }
    decision = guard_spoken_copy(
        candidate,
        evidence=evidence,
        required=True,
        purpose=f"gap_prior_fallback[{category}]",
    )
    text = str(decision.get("text") or "").strip()
    if text:
        return text
    # Required guard still emptied (omit/block): never seed blank high-gap VO,
    # and never seed the phrase the guard just refused (ISSUES 123). Take the
    # first pool phrase the guard speaks in this context.
    for phrase in _COURTESY_SEED_POOL:
        probe = guard_spoken_copy(
            phrase,
            evidence=evidence,
            required=True,
            purpose=f"gap_prior_fallback[{category}]",
        )
        spoken = str(probe.get("text") or "").strip()
        if spoken:
            return spoken
    return diversified

def enrich_line_with_prior_context(
    line: dict[str, Any],
    *,
    prior: dict[str, Any] | None,
    density_forced: bool = False,
) -> dict[str, Any]:
    """Stamp provenance fields onto an interviewer line from prior_native_context."""
    out = dict(line)
    if not isinstance(prior, dict):
        # Still coerce nulls left by LLM merges when no prior packet is available.
        for key in ("prior_impact_beat", "prior_complete_thought", "density_forced"):
            if key in out:
                out[key] = bool(out.get(key))
        return out
    sid = str(prior.get("segment_id") or "").strip()
    out["prior_segment_id"] = sid or None
    out["prior_impact_beat"] = bool(prior.get("prior_impact_beat"))
    out["prior_complete_thought"] = bool(prior.get("prior_complete_thought"))
    out["density_forced"] = bool(density_forced or out.get("density_forced"))
    return out


def apply_prior_context_to_density_seed(
    ctx: RunContext,
    *,
    target_segment_id: str,
    category: str,
    text: str,
) -> tuple[str, str, dict[str, Any] | None, dict[str, Any]]:
    """Relocate micro targets + rewrite interruptive/density stock using prior context.

    Returns (final_target_id, final_text, prior_packet, provenance_fields).
    """
    settings = prior_context_cfg()
    ordered, by_id, chapters = load_ordered_and_segments(ctx)
    sid = str(target_segment_id)
    if settings.get("relocate_micro_targets", True):
        sid = next_substantive_target(
            preferred_id=sid,
            ordered_ids=ordered,
            segments_by_id=by_id,
            cfg=settings,
        )
    prior = build_prior_native_context(
        target_segment_id=sid,
        ordered_ids=ordered,
        segments_by_id=by_id,
        chapters=chapters,
        cfg=settings,
    )
    final_text = text
    if settings.get("rewrite_density_seeds", True):
        if is_interruptive_opener(text) or (prior and prior.get("prior_impact_beat")):
            final_text = courtesy_seed_text(
                prior, category=category, target_segment_id=sid
            )
    prov = enrich_line_with_prior_context(
        {"targets_segment_id": sid, "text": final_text, "line_category": category},
        prior=prior,
        density_forced=True,
    )
    return sid, final_text, prior, prov


def build_prior_context_volley_turns(stage_input: dict[str, Any]) -> list[dict[str, str]]:
    """Sequential user/assistant turns that condition the gap framing LLM on prior beats."""
    settings = prior_context_cfg()
    if not settings.get("enabled", True) or not settings.get("volley_turns_enabled", True):
        return []
    highlights = stage_input.get("prior_impact_highlights")
    contexts = stage_input.get("prior_native_contexts")
    if not isinstance(highlights, list):
        highlights = []
    if not highlights and isinstance(contexts, dict):
        for tid, pkt in list(contexts.items())[:12]:
            if isinstance(pkt, dict):
                highlights.append(
                    {
                        "before_target": tid,
                        "prior_segment_id": pkt.get("segment_id"),
                        "prior_impact_beat": pkt.get("prior_impact_beat"),
                        "quote_span": pkt.get("quote_span"),
                    }
                )
    if not highlights and not isinstance(contexts, dict):
        return []

    # Cap volley payload size.
    sample = []
    for h in highlights[:8]:
        if not isinstance(h, dict):
            continue
        sample.append(
            {
                "prior_segment_id": h.get("prior_segment_id"),
                "before_target": h.get("before_target"),
                "prior_impact_beat": bool(h.get("prior_impact_beat")),
                "quote_span": h.get("quote_span"),
                "chapter_title": h.get("chapter_title"),
                "target_is_micro": h.get("target_is_micro"),
            }
        )
    user1 = (
        "PRIOR NATIVE BEATS (immediate previous ordered segments before VO targets).\n"
        "Absorb these before writing host lines. Mic-drop / complete closes must be honored — "
        "do not interrupt them with stock 'pause you there' language.\n\n"
        f"{sample if sample else 'No prior beats listed; still use prior_native_contexts in the stage input JSON.'}"
    )
    assistant1 = (
        "Understood. I will condition every interviewer line on prior_native_contexts for its "
        "targets_segment_id. After prior_impact_beat or a complete strong close I will use courteous "
        "acknowledge / soft-bridge / follow-from-what-was-said wording only, never interruptive openers, "
        "and I will not aim framing questions at micro backchannels like 'Okay.'"
    )
    user2 = (
        "Now write the gap framing interviewer_lines (and optional gap_framing_plan) for the full "
        "stage input in the next user message. Apply prior_native_context_policy strictly."
    )
    return [
        {"role": "user", "content": user1},
        {"role": "assistant", "content": assistant1},
        {"role": "user", "content": user2},
    ]


def stamp_lines_prior_provenance(
    ctx: RunContext,
    lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure every line carries prior_segment_id / prior_impact_beat when resolvable."""
    settings = prior_context_cfg()
    if not settings.get("enabled", True):
        return lines
    ordered, by_id, chapters = load_ordered_and_segments(ctx)
    out: list[dict[str, Any]] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        row = dict(line)
        tid = str(row.get("targets_segment_id") or "").strip()
        if not tid:
            out.append(row)
            continue
        prior = build_prior_native_context(
            target_segment_id=tid,
            ordered_ids=ordered,
            segments_by_id=by_id,
            chapters=chapters,
            cfg=settings,
        )
        out.append(enrich_line_with_prior_context(row, prior=prior, density_forced=bool(row.get("density_forced"))))
    return out


def write_gap_vo_context_audit(ctx: RunContext, lines: list[dict[str, Any]]) -> None:
    """Debug/smoke artifact: sampled lines with prior provenance + courtesy flags."""
    samples: list[dict[str, Any]] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        text = str(line.get("text") or "")
        samples.append(
            {
                "line_id": line.get("line_id"),
                "targets_segment_id": line.get("targets_segment_id"),
                "prior_segment_id": line.get("prior_segment_id"),
                "prior_impact_beat": bool(line.get("prior_impact_beat")),
                "prior_complete_thought": bool(line.get("prior_complete_thought")),
                "density_forced": bool(line.get("density_forced")),
                "interruptive_opener": is_interruptive_opener(text),
                "courtesy_ok": not (
                    bool(line.get("prior_impact_beat")) and is_interruptive_opener(text)
                ),
                "text_preview": text[:160],
            }
        )
        if len(samples) >= 40:
            break
    doc = {
        "version": 1,
        "sample_count": len(samples),
        "lines": samples,
        "policy": (prior_context_cfg()),
    }
    try:
        ctx.write_json(
            GAP_VO_CONTEXT_AUDIT_REL,
            doc,
            stage_key="gap_framing_compose",
        )
    except Exception:
        pass


def courtesy_violations(lines: list[dict[str, Any]]) -> list[str]:
    """Return human-readable courtesy violations (impact prior + interruptive opener)."""
    errs: list[str] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        if line.get("prior_impact_beat") and is_interruptive_opener(str(line.get("text") or "")):
            lid = line.get("line_id") or line.get("targets_segment_id") or "?"
            errs.append(f"{lid}: interruptive opener after prior_impact_beat")
    return errs
