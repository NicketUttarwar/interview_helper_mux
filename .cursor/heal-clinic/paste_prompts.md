# Heal Clinic — paste prompts

Campaign: [`.cursor/plans/heal_clinic.plan.md`](../plans/heal_clinic.plan.md)  
Skill: [`.cursor/skills/heal-clinic/SKILL.md`](../skills/heal-clinic/SKILL.md)

---

## Next bug (your main continue button)

```
/heal-clinic-next
Follow .cursor/skills/heal-clinic/SKILL.md
Read .cursor/heal-clinic/STEP_OFF.md, queue.md, ledger.md.
Pick the next class that needs L1 or options (or is awaiting my verdict — summarize and stop).
Work that class only. Code is king. Simple language.
If L1 missing → discover. If L1 done and no options → write options packet (A/B/C + Defer, surgical + bigger deterministic, worst cases, recommendation, cousin suggestions).
No product patches. End with YOUR NEXT ACTIONS and a fresh /heal-clinic-next paste for me.
```

---

## Discover (cause map — one class)

```
/heal-clinic-discover CLASS=<id>
Follow .cursor/skills/heal-clinic/SKILL.md
Class pack: .cursor/heal-clinic/classes/<id>/
Write/update dossier.md + possibility.md from HEAD code only.
Tag IN_CODE | DOC_ONLY_UNVERIFIED | CODE_DOC_CONFLICT | UNKNOWN.
Prior exec_* = HINT only if I named a folder; else ignore ASSETS/executions/.
Brain 0.2.0. Partial lens + all-modes impact notes.
No product patches. No options packet yet unless I also asked for options.
End with plain-language “what’s going wrong” + paste for /heal-clinic-options CLASS=<id>.
```

---

## Options (you decide later)

```
/heal-clinic-options CLASS=<id>
Follow .cursor/skills/heal-clinic/SKILL.md
Read classes/<id>/possibility.md (discover first if thin).
Write classes/<id>/options.md from templates/options_packet.md.
Required: Option A surgical, Option B bigger deterministic SSOT (or say why B is not real), Option C alternate, Defer.
Each: pros, cons, real-world worst case, Partial impact, all-modes impact, tests.
TL;DR + contextual recommendation + what recommendation gives up + cousin classes to open next.
Simple language. Spawn subagents as needed; merge into one options.md.
No product patches. No deciding for me — recommend only.
End with /heal-clinic-answer paste examples and /heal-clinic-next.
```

---

## Your answer

```
/heal-clinic-answer CLASS=<id> VERDICT=A|B|C|Defer|custom:<text>
Follow .cursor/skills/heal-clinic/SKILL.md
Append to classes/<id>/decisions.md and update ledger.md + STEP_OFF.md.
Do not implement unless I also paste /heal-clinic-implement.
```

---

## Suggest cousins / bigger SSOT

```
/heal-clinic-suggest-cousins CLASS=<id>
Follow .cursor/skills/heal-clinic/SKILL.md
From this class map/options, list related heal classes and any cross-class deterministic SSOT opportunity.
Update cross_class_patterns.md if the same footgun appears in ≥2 classes.
No patches. Simple language. End with /heal-clinic-next.
```

---

## Implement (Wave 2 only — after my verdict)

```
/heal-clinic-implement CLASS=<id>
Wave 2 explicit. Follow .cursor/skills/heal-clinic/SKILL.md
Read options.md + decisions.md verdict. Patch only the chosen option’s unambiguous work.
MUX_FORENSICS=0 cascade/matrix tests. Prefer mode-wide SSOT. No local heavy ML campaigns.
Update ledger L3. Stop on needs_you.
```

---

## Continue mid-class

```
/heal-clinic-continue CLASS=<id> LAYER=L1|options|L3
My notes (optional): ...
Follow .cursor/skills/heal-clinic/SKILL.md
```

---

## Readiness (Wave 3)

```
/heal-clinic-readiness
Follow .cursor/skills/heal-clinic/SKILL.md
Score all five classes into heal_readiness.md. Plain language Partial + all-modes odds.
No patches. No exec_* archaeology unless I name folders.
```
