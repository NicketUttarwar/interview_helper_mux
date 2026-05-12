-- Canonical backbone order (see docs/execution/orchestration-component-map.md).
INSERT OR IGNORE INTO pipeline_stage (slug, ordinal, display_name, notes) VALUES
  ('capture', 10, 'Capture', 'Source recording'),
  ('ingest', 20, 'Ingest', 'Normalization, checksums, chunking'),
  ('transcription', 30, 'Transcription', 'STT + optional diarization'),
  ('segmentation', 40, 'Segmentation', 'Boundaries / topics'),
  ('scoring_and_selection', 50, 'Scoring & selection', 'Rank, diversity, LLM assist'),
  ('snippet_store', 60, 'Snippet store', 'Manifests, provenance'),
  ('audio_editing', 70, 'Audio editing', 'Cuts, crossfades, room tone'),
  ('assembly_and_mux', 80, 'Assembly & mux', 'EDL / graph / edge costs'),
  ('mastering_and_export', 90, 'Mastering & export', 'LUFS, chapters, export'),
  ('human_review', 1000, 'Human review (control plane)', 'Overlaid after score/mux/gates; not a backbone physics stage');
