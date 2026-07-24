/** Coordinate GUI audio so play/pause stays reliable across stages. */

const registry = new Set<HTMLAudioElement>();

/** HTMLMediaElement.HAVE_FUTURE_DATA — numeric so unit tests need no DOM globals. */
const HAVE_FUTURE_DATA = 3;

function absoluteUrl(url: string): string {
  try {
    return new URL(
      url,
      typeof window !== "undefined" ? window.location.href : "http://localhost/",
    ).href;
  } catch {
    return url;
  }
}

/**
 * Register an `<audio>` element so starting playback pauses other players.
 * Returns an unregister cleanup for useEffect.
 */
export function registerExclusiveAudio(el: HTMLAudioElement): () => void {
  const onPlay = () => {
    pauseOtherAudio(el);
  };
  registry.add(el);
  el.addEventListener("play", onPlay);
  return () => {
    el.removeEventListener("play", onPlay);
    registry.delete(el);
  };
}

export function pauseOtherAudio(except: HTMLAudioElement | null | undefined): void {
  for (const other of registry) {
    if (other !== except && !other.paused) {
      other.pause();
    }
  }
  if (typeof document === "undefined") return;
  document.querySelectorAll("audio").forEach((node) => {
    const audio = node as HTMLAudioElement;
    if (audio !== except && !audio.paused) {
      audio.pause();
    }
  });
}

function waitForCanPlay(el: HTMLAudioElement, timeoutMs = 20_000): Promise<void> {
  if (el.readyState >= HAVE_FUTURE_DATA) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("Audio load timed out"));
    }, timeoutMs);
    const onCanPlay = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("Audio failed to load"));
    };
    const cleanup = () => {
      window.clearTimeout(timer);
      el.removeEventListener("canplay", onCanPlay);
      el.removeEventListener("error", onError);
    };
    el.addEventListener("canplay", onCanPlay);
    el.addEventListener("error", onError);
  });
}

/**
 * Swap `src` if needed, wait until playable, optionally restart, then play.
 * Safer than `el.src = url; el.currentTime = 0; el.play()` races.
 */
export async function loadAndPlay(
  el: HTMLAudioElement,
  url: string,
  opts?: { restart?: boolean },
): Promise<void> {
  const restart = opts?.restart !== false;
  const next = absoluteUrl(url);
  const current = el.currentSrc || el.src;
  if (current !== next) {
    el.pause();
    el.src = url;
    el.load();
  }
  await waitForCanPlay(el);
  if (restart) {
    try {
      el.currentTime = 0;
    } catch {
      /* ignore until metadata is ready */
    }
  }
  pauseOtherAudio(el);
  await el.play();
}

export async function togglePlayPause(
  el: HTMLAudioElement | null | undefined,
): Promise<"play" | "pause" | "noop"> {
  if (!el) return "noop";
  if (el.paused) {
    pauseOtherAudio(el);
    await el.play();
    return "play";
  }
  el.pause();
  return "pause";
}

/** Test helper — clear exclusive registry between cases. */
export function _resetAudioPlaybackRegistryForTests(): void {
  registry.clear();
}
