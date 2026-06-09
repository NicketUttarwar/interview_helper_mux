/** Normalize backend source-audio hash fields to the 12-char short form. */
export function sourceHashShort(fields?: {
  source_audio_hash_short?: string | null;
  source_audio_hash?: string | null;
} | null): string | null {
  if (!fields) return null;
  if (fields.source_audio_hash_short) return fields.source_audio_hash_short;
  const full = fields.source_audio_hash;
  if (!full) return null;
  const clean = full.replace(/[^a-f0-9]/gi, "").toLowerCase();
  return clean.slice(0, 12) || null;
}
