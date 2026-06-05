import { useCallback, useRef, useState } from "react";
import type { NleState } from "../types";

const MAX_HISTORY = 30;

export interface HistoryEntry {
  id: number;
  label: string;
  state: NleState;
}

export function useNleHistory() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [pointer, setPointer] = useState(-1);
  const pointerRef = useRef(-1);
  const idRef = useRef(0);

  const syncPointer = (p: number) => {
    pointerRef.current = p;
    setPointer(p);
  };

  const push = useCallback((state: NleState, label = "Timeline edit") => {
    const entry: HistoryEntry = {
      id: ++idRef.current,
      label,
      state: JSON.parse(JSON.stringify(state)) as NleState,
    };
    setEntries((hist) => {
      const ptr = pointerRef.current;
      const trimmed = ptr >= 0 ? hist.slice(0, ptr + 1) : [];
      const nextHist = [...trimmed, entry].slice(-MAX_HISTORY);
      syncPointer(nextHist.length - 1);
      return nextHist;
    });
  }, []);

  const canUndo = pointer > 0;
  const canRedo = pointer >= 0 && pointer < entries.length - 1;

  const undoState = useCallback((): NleState | null => {
    const ptr = pointerRef.current;
    if (ptr <= 0) return null;
    const nextPtr = ptr - 1;
    syncPointer(nextPtr);
    return entries[nextPtr]?.state ?? null;
  }, [entries]);

  const redoState = useCallback((): NleState | null => {
    const ptr = pointerRef.current;
    if (ptr >= entries.length - 1) return null;
    const nextPtr = ptr + 1;
    syncPointer(nextPtr);
    return entries[nextPtr]?.state ?? null;
  }, [entries]);

  const restoreTo = useCallback(
    (index: number): NleState | null => {
      if (index < 0 || index >= entries.length) return null;
      syncPointer(index);
      return entries[index].state;
    },
    [entries],
  );

  const reset = useCallback(() => {
    setEntries([]);
    syncPointer(-1);
  }, []);

  return {
    entries,
    pointer,
    push,
    canUndo,
    canRedo,
    undoState,
    redoState,
    restoreTo,
    reset,
  };
}
