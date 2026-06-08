import {
  questionsToText,
  textToQuestions,
  textToThemes,
  themesToText,
} from "../../utils/profile";
import type { AnalysisState } from "../../types";

export interface ProfileFormState {
  title: string;
  summary: string;
  thesis: string;
  themes: string;
  questions: string;
  tone: string;
  toneClass: string;
  formatClass: string;
  formatNotes: string;
  pacing: string;
  intStyle: string;
  eeStyle: string;
  notes: string;
}

export function loadProfileToForm(st: AnalysisState): ProfileFormState {
  const ident = st.interview_identity || {};
  const narrative = st.narrative || {};
  const style = st.style || {};
  return {
    title: ident.title || "",
    summary: ident.one_line_summary || "",
    thesis: narrative.thesis || "",
    themes: themesToText(st.themes),
    questions: questionsToText(st.major_questions),
    tone: style.tone || "",
    toneClass: style.tone_class || "",
    formatClass: style.format_class || "",
    formatNotes: style.format_notes || "",
    pacing: style.pacing || "",
    intStyle: style.interviewer_style || "",
    eeStyle: style.interviewee_style || "",
    notes: st.operator_notes || "",
  };
}

export function collectAnalysisProfileFromForm(
  form: ProfileFormState,
  base: AnalysisState | null,
): AnalysisState {
  return {
    ...(base || {}),
    interview_identity: {
      ...(base?.interview_identity || {}),
      title: form.title.trim(),
      one_line_summary: form.summary.trim(),
    },
    narrative: {
      ...(base?.narrative || {}),
      thesis: form.thesis.trim(),
    },
    themes: textToThemes(form.themes),
    major_questions: textToQuestions(form.questions),
    style: {
      ...(base?.style || {}),
      tone: form.tone.trim(),
      tone_class: form.toneClass.trim() || undefined,
      format_class: form.formatClass.trim() || undefined,
      format_notes: form.formatNotes.trim(),
      pacing: form.pacing.trim(),
      interviewer_style: form.intStyle.trim(),
      interviewee_style: form.eeStyle.trim(),
    },
    operator_notes: form.notes.trim(),
  };
}
