# Value metrics library — spike definitions

Operational definitions for **human** and **model-proxy** measures used in [phase3-spike-framework.md](./phase3-spike-framework.md). All studies are **audio-only** (plus transcript where noted).

## 1. Human scales

### 1.1 Listener Likert (1–5)

Used for LEX-A, LEX-B, LEX-C and section-local dimensions when adapted.

| Score | Anchor |
|-------|--------|
| 1 | Strongly disagree / very poor |
| 3 | Neutral |
| 5 | Strongly agree / excellent |

### 1.2 Retell protocol (COM-A, COM-B)

1. Listener hears clip or chapter **without** reading transcript.
2. Free recall: write thesis + two claims + one contrast.
3. Rater scores **COM-A** (thesis + claims present), **COM-B** (contrast accurate) binary or 1–5.

### 1.3 Operator timed task (CRE-B)

1. Task definition: e.g. “pick best 60s highlight” or “approve segment boundaries.”
2. Same operators with and without tool hints; measure wall time and self-rated confidence (CRE-B, CRE-C).

### 1.4 Minimum N

Document N per spike; prefer **N ≥ 8** listeners for exploratory studies; **N ≥ 3** operators for CRE tasks in early spikes.

## 2. Model proxies (allowed with caveats)

| Proxy | May inform | Must not |
|-------|------------|-----------|
| SSL state delta | MEC-A, boundary hints | Replace human boundary truth |
| CLAP similarity top-K | Candidate ranking | Solely determine final air without listen |
| Event detector confidence | Hook candidates | Auto-cut laughter without operator |
| MOS-like predictor (e.g. NISQA-class) | LEX-B regions | Claim “broadcast legal” without loudness law check |

Every proxy row in a spike sheet must include **known failure modes** (e.g. music as speech, bias toward certain accents).

## 3. Ethical stance (product)

- **Authentic communication** beats manipulative “engagement hacking.” Signals that inflate perceived drama without fidelity to the guest’s intent score **down** on COM-A in veto review.
- Paralinguistic tagging must respect dignity: no public scoring of individual vulnerability for entertainment.

## 4. Clip A/B protocol

1. Match loudness perceptually (rough EBU-style) before compare.
2. Randomize order A/B.
3. Forced choice + optional Likert; record reason in one line.

## 5. Linkage to rubric IDs

See [phase3-spike-framework.md](./phase3-spike-framework.md) for LEX-*, COM-*, CRE-*, MEC-*, MOO-* definitions.
