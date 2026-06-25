import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

const OVERSCROLL_THRESHOLD_PX = 72;

/**
 * When the user scrolls past the bottom of a container, run onRetry once
 * and show a small loading indicator.
 */
export function useOverscrollRetry(
  containerRef: RefObject<HTMLElement | null>,
  onRetry: () => Promise<void> | void,
  enabled = true,
): { overscrollLoading: boolean } {
  const [overscrollLoading, setOverscrollLoading] = useState(false);
  const overscrollAccumRef = useRef(0);
  const touchStartYRef = useRef<number | null>(null);
  const busyRef = useRef(false);
  const onRetryRef = useRef(onRetry);
  onRetryRef.current = onRetry;

  const triggerRetry = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    overscrollAccumRef.current = 0;
    setOverscrollLoading(true);
    try {
      await onRetryRef.current();
    } finally {
      busyRef.current = false;
      setOverscrollLoading(false);
    }
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !enabled) return;

    const atBottom = () => el.scrollTop + el.clientHeight >= el.scrollHeight - 4;

    const onWheel = (e: WheelEvent) => {
      if (!atBottom() || e.deltaY <= 0) {
        overscrollAccumRef.current = 0;
        return;
      }
      overscrollAccumRef.current += e.deltaY;
      if (overscrollAccumRef.current >= OVERSCROLL_THRESHOLD_PX) {
        void triggerRetry();
      }
    };

    const onTouchStart = (e: TouchEvent) => {
      if (!atBottom()) {
        touchStartYRef.current = null;
        return;
      }
      touchStartYRef.current = e.touches[0]?.clientY ?? null;
    };

    const onTouchMove = (e: TouchEvent) => {
      const startY = touchStartYRef.current;
      if (startY == null || !atBottom()) return;
      const y = e.touches[0]?.clientY;
      if (y == null) return;
      const pullUp = startY - y;
      if (pullUp >= OVERSCROLL_THRESHOLD_PX) {
        touchStartYRef.current = null;
        void triggerRetry();
      }
    };

    el.addEventListener("wheel", onWheel, { passive: true });
    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchmove", onTouchMove, { passive: true });
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
    };
  }, [containerRef, enabled, triggerRetry]);

  return { overscrollLoading };
}
