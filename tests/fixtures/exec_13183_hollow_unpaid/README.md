# Fixture: exec_13183 Dig #2 hollow unpaid (music remaster)

Reconstitutes the i10 failure mode: speech-first mix seat + music_epoch remaster
owed → orphan promote must refuse `.stage_done/mix`.

Live fingerprint: `speech_first_remaster_pending` on junction while mix looked done.

WAVs are not committed — tests mint a tiny `master/assembly.wav` and age its mtime.
