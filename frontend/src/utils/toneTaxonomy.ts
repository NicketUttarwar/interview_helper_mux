/** Tone and format taxonomy — mirrors src/interview_mux/tone_taxonomy.py */

export const TONE_CLASS_VALUES = [
  "journalistic",
  "conversational",
  "investor",
  "technical",
  "human_interest",
] as const;

export type ToneClass = (typeof TONE_CLASS_VALUES)[number];

export const FORMAT_CLASS_VALUES = [
  "one_on_one",
  "panel",
  "fireside",
  "technical_deep_dive",
  "media_profile",
  "debate",
] as const;

export type FormatClass = (typeof FORMAT_CLASS_VALUES)[number];

export function formatClassLabel(value: string): string {
  return value.replace(/_/g, " ");
}
