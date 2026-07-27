import type { RefinementBible } from "../../types";

interface Props {
  bible?: RefinementBible;
}

/** Lightweight story snapshot — thesis / chapters / host lines — read-only, no editing here. */
export function RefinementBibleMiniView({ bible }: Props) {
  if (!bible || (!bible.thesis && !bible.chapters?.length && !bible.host_lines?.length)) {
    return null;
  }

  return (
    <details className="refinement-bible-mini-view" data-testid="refinement-bible-mini-view">
      <summary className="muted sm">Story bible (mini view)</summary>
      {bible.thesis ? (
        <p className="hint sm refinement-bible-thesis">
          <strong>Thesis:</strong> {bible.thesis}
        </p>
      ) : null}
      {bible.chapters?.length ? (
        <ol className="refinement-bible-chapters">
          {bible.chapters.map((title, i) => (
            <li key={`${title}-${i}`}>{title}</li>
          ))}
        </ol>
      ) : null}
      {bible.host_lines?.length ? (
        <>
          <p className="hint sm refinement-bible-host-lines-label">Host lines (sample):</p>
          <ul className="refinement-bible-host-lines">
            {bible.host_lines.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        </>
      ) : null}
    </details>
  );
}
