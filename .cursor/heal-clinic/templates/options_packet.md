# Options packet — {{CLASS_ID}}

status: awaiting_operator | decided | implemented | deferred  
class_plain_name: {{CLASS_PLAIN}}  
brain: 0.2.0 | code_is_king: true

## TL;DR (read this first — simple language)

- What’s going wrong (1–2 sentences):
- What you’d notice in a real Partial (or Full-auto) run:
- Why it matters for error-free execution:
- **Agent recommendation:** Option _ — (one line why)
- What that recommendation **gives up**:

## Options at a glance

| Option | One-line idea | Best if you want… | Worst trade-off |
|--------|---------------|-------------------|-----------------|
| A — Surgical | | Smallest honest fix | May leave cousins open |
| B — Bigger deterministic | | One SSOT closes the family | Larger blast radius |
| C — Alternate | | … | … |
| Defer | Wait / Debug / more map | More evidence | Odds stay low longer |

---

## Option A — Surgical (smallest honest fix)

**What we would do** (plain steps; then code pointers):

**Pros:**

**Cons:**

**Real-world worst case if we choose A:**  
(What breaks on a Mohan Partial / Full-auto night run if A is wrong or incomplete?)

| Axis | Assessment |
|------|------------|
| Partial certainty | |
| All-modes / Full-auto | |
| Cousin closure | |
| Complexity left | |
| What you give up | |
| Implement cost | |
| Regression risk | |
| Reversibility | |
| FULL_AUTO_REGRESSION_RISK | no \| yes — explain |

**Tests we would add** (`MUX_FORENSICS=0`):

---

## Option B — Bigger deterministic (family / SSOT root)

**What we would do** (plain steps; then code pointers):

**Pros:**

**Cons:**

**Real-world worst case if we choose B:**

| Axis | Assessment |
|------|------------|
| Partial certainty | |
| All-modes / Full-auto | |
| Cousin closure | |
| Complexity left | |
| What you give up | |
| Implement cost | |
| Regression risk | |
| Reversibility | |
| FULL_AUTO_REGRESSION_RISK | no \| yes — explain |

**Tests we would add** (`MUX_FORENSICS=0`):

---

## Option C — Alternate

**What we would do:**

**Pros:**

**Cons:**

**Real-world worst case if we choose C:**

(Same axis table as A/B.)

**Tests we would add:**

---

## Option Defer

**What we would wait for:** more HEAD map · named Debug pass · live soak observe · cousin class first  

**Risk if we wait:**

---

## Recommendation (not a decision)

- Preferred: Option _
- Why this is best for **error-free Partial**:
- Why this still helps **all modes** (or honest Partial-only caveat):
- Honest downside:
- Devil’s-advocate note (why someone would pick the other letter):

## Cousins to investigate next (suggestions)

| Class id | Why related | Bigger shared SSOT? |
|----------|-------------|---------------------|
| | | yes/no — |

Update [`../../cross_class_patterns.md`](../../cross_class_patterns.md) if ≥2 classes share one root.

## Evidence appendix

- HEAD code (**SSOT**):
- Docs / Partial Zero / Stage Clinic (**hints** — verify or drop):
- Named exec HINT (only if operator named folder):
- Swarm raw notes: `classes/{{CLASS_ID}}/solution_swarm/`

## Your verdict (operator fills)

- choice: A | B | C | Defer | custom:
- notes:
- date:

## YOUR NEXT ACTIONS

1. Optional: `/heal-clinic-suggest-cousins CLASS={{CLASS_ID}}` or Ask/Debug for one unclear site.
2. Paste: `/heal-clinic-answer CLASS={{CLASS_ID}} VERDICT=A` (or B/C/Defer/custom:…).
3. After verdict, when ready: `/heal-clinic-implement CLASS={{CLASS_ID}}`
4. Or skip to another bug: `/heal-clinic-next`
