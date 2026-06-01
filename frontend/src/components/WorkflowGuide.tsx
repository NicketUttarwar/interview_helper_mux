const STEPS = [
  {
    phase: "Start",
    detail: "Pick input audio and what you are making (full episode, reel, or description).",
  },
  {
    phase: "Prepare",
    detail: "Transcribe with AWS, then review and fix low-confidence clips (G0).",
  },
  {
    phase: "Understand",
    detail: "Run analysis, shape the story, lock the profile for full-master edits.",
  },
  {
    phase: "Complete",
    detail: "Record VO pickups if needed (G1), confirm output type (G2).",
  },
  {
    phase: "Create → Ship",
    detail: "Build preview or highlights, add sound, export master or copy show text.",
  },
];

export function WorkflowGuide() {
  return (
    <section className="panel workflow-guide">
      <h3>How this app works</h3>
      <ol className="workflow-steps">
        {STEPS.map((s, i) => (
          <li key={s.phase}>
            <span className="workflow-step-num">{i + 1}</span>
            <div>
              <strong>{s.phase}</strong>
              <p className="muted">{s.detail}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="hint workflow-tip">
        Use the <strong>Pipeline</strong> tab for stages. When something needs you, an{" "}
        <strong>Action</strong> badge appears — open it to review transcripts, record VO,
        or grant API access (AWS Transcribe, OpenAI, ElevenLabs).
      </p>
    </section>
  );
}
