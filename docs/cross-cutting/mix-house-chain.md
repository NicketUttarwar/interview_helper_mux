# Mix house chain (policy)

Audacity-class **order**, not a full DAW UI. Speech / [speaker volleys](./volley-glossary.md) first.

1. Preclean / hygiene (optional DeepFilter)  
2. Edit — keep speaker volleys intact; fades at edges  
3. Per-speaker level match  
4. Place VO at volley boundaries / framing-before-impact  
5. Place beds under active speaker volleys; stingers at hinges  
6. Duck — speech wins under volleys (`duck_under_speech_db`, TBIY tiers)  
7. Glue / safety limiter  
8. Loudnorm → `master/master.wav` (−16 LUFS podcast)  
9. QC — `verify_master`, intelligibility, soundscape remux capped  

See [soundscape-policy.md](./soundscape-policy.md) · [local-audio-stack.md](./local-audio-stack.md).
