import { useLayoutEffect, useRef, useState, type RefObject } from "react";

export const ACTIVITY_LOG_PANEL_HEIGHT_CAP_MULTIPLIER = 2;

export function capActivityLogPanelHeight(baseHeight: number): number {
  return Math.round(baseHeight * ACTIVITY_LOG_PANEL_HEIGHT_CAP_MULTIPLIER);
}

export function useActivityLogPanelHeightCap(enabled: boolean): {
  panelRef: RefObject<HTMLElement | null>;
  maxPanelHeight: number | undefined;
} {
  const panelRef = useRef<HTMLElement>(null);
  const baseHeightRef = useRef<number | null>(null);
  const [maxPanelHeight, setMaxPanelHeight] = useState<number | undefined>();

  useLayoutEffect(() => {
    if (!enabled) return;
    const el = panelRef.current;
    if (!el || baseHeightRef.current != null) return;

    const capture = () => {
      if (baseHeightRef.current != null) return;
      const height = el.getBoundingClientRect().height;
      if (height <= 0) return;
      baseHeightRef.current = height;
      setMaxPanelHeight(capActivityLogPanelHeight(height));
    };

    capture();
    const ro = new ResizeObserver(() => {
      if (baseHeightRef.current != null) {
        ro.disconnect();
        return;
      }
      capture();
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [enabled]);

  return { panelRef, maxPanelHeight };
}
