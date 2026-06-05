import type { TimelineSegment } from "../../../types";
import type { TimelineFilters } from "../../../utils/nleHelpers";

interface Props {
  filters: TimelineFilters;
  segments: TimelineSegment[];
  matchCount: number;
  onChange: (patch: Partial<TimelineFilters>) => void;
  onSelectSearchResult: (segId: string, startMs: number) => void;
}

const TYPES = [
  "",
  "interviewer_question",
  "interviewee_answer",
  "interviewer_reaction",
  "setup",
  "aside",
  "coda",
];

export function TimelineFilterBar({
  filters,
  segments,
  matchCount,
  onChange,
  onSelectSearchResult,
}: Props) {
  const searchResults =
    filters.search.trim().length >= 2
      ? segments
          .filter((s) => {
            const q = filters.search.toLowerCase();
            return (
              (s.text || "").toLowerCase().includes(q) ||
              (s.segment_id || "").toLowerCase().includes(q)
            );
          })
          .slice(0, 8)
      : [];

  return (
    <div className="timeline-filter-bar">
      <select
        value={filters.type}
        onChange={(e) => onChange({ type: e.target.value })}
        aria-label="Filter by type"
      >
        <option value="">All types</option>
        {TYPES.filter(Boolean).map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
      <select
        value={filters.speakerRole}
        onChange={(e) => onChange({ speakerRole: e.target.value })}
        aria-label="Filter by speaker"
      >
        <option value="">All speakers</option>
        <option value="interviewer">Interviewer</option>
        <option value="interviewee">Interviewee</option>
        <option value="unknown">Unknown</option>
      </select>
      <select
        value={filters.inSelection}
        onChange={(e) => onChange({ inSelection: e.target.value })}
      >
        <option value="">Selection: any</option>
        <option value="yes">In selection</option>
        <option value="no">Off selection</option>
      </select>
      <select
        value={filters.excluded}
        onChange={(e) => onChange({ excluded: e.target.value })}
      >
        <option value="">Excluded: any</option>
        <option value="no">Active only</option>
        <option value="yes">Excluded only</option>
      </select>
      <select value={filters.hasVo} onChange={(e) => onChange({ hasVo: e.target.value })}>
        <option value="">VO: any</option>
        <option value="yes">Has VO</option>
        <option value="no">No VO</option>
      </select>
      <select value={filters.hasFlags} onChange={(e) => onChange({ hasFlags: e.target.value })}>
        <option value="">Flags: any</option>
        <option value="yes">Flagged</option>
        <option value="no">Not flagged</option>
      </select>
      <input
        type="search"
        className="timeline-filter-search"
        placeholder="Search transcript…"
        value={filters.search}
        onChange={(e) => onChange({ search: e.target.value })}
      />
      <label className="timeline-filter-hide">
        <input
          type="checkbox"
          checked={filters.hideNonMatching}
          onChange={(e) => onChange({ hideNonMatching: e.target.checked })}
        />
        Hide non-matching
      </label>
      <span className="muted timeline-filter-count">{matchCount} segments</span>
      {searchResults.length ? (
        <ul className="timeline-search-results">
          {searchResults.map((s) => (
            <li key={s.segment_id}>
              <button
                type="button"
                className="btn sm ghost"
                onClick={() => onSelectSearchResult(s.segment_id!, s.start_ms)}
              >
                {s.segment_id}: {(s.text || "").slice(0, 48)}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
