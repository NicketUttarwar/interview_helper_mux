export function ElevenLabsBlockedPanel({ onOpen }: { onOpen: () => void }) {
  return (
    <div className="quality-offer-card">
      <p className="hint">
        <strong>G1.5 required:</strong> review and approve ElevenLabs prompts before
        generation.
      </p>
      <p className="muted">
        Open <strong>ElevenLabs prompt craft</strong> to edit prompts, tune influence,
        and approve.
      </p>
      <div className="flow-choice">
        <button type="button" className="btn primary sm" onClick={onOpen}>
          Open prompt craft
        </button>
      </div>
    </div>
  );
}
