import { useApp } from "../../context/AppContext";

export function SourceAudioHashBadge({
  hashShort,
  hashFull,
  matched,
  label = "Source audio",
}: {
  hashShort?: string | null;
  hashFull?: string | null;
  matched?: boolean;
  label?: string;
}) {
  const { showToast } = useApp();
  if (!hashShort) return null;

  const copy = () => {
    const value = hashFull || hashShort;
    void navigator.clipboard.writeText(value).then(() => {
      showToast("Audio hash copied.");
    });
  };

  return (
    <span className="source-hash-badge-wrap">
      <span className="source-hash-badge-label muted">{label}</span>
      <button
        type="button"
        className={`hash-chip mono hash-chip-btn${matched ? " hash-chip-match" : ""}`}
        title={hashFull || hashShort}
        onClick={copy}
      >
        {hashShort}
        {matched ? <span className="hash-match-indicator"> · same audio</span> : null}
      </button>
    </span>
  );
}
