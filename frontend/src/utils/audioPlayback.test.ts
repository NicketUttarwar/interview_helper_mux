import { afterEach, describe, expect, it, vi } from "vitest";
import {
  _resetAudioPlaybackRegistryForTests,
  loadAndPlay,
  pauseOtherAudio,
  registerExclusiveAudio,
  togglePlayPause,
} from "./audioPlayback";

function mockAudio(overrides: Partial<HTMLAudioElement> = {}): HTMLAudioElement {
  const listeners = new Map<string, Set<EventListener>>();
  const el = {
    paused: true,
    src: "",
    currentSrc: "",
    currentTime: 0,
    readyState: 4,
    play: vi.fn(async function (this: HTMLAudioElement) {
      this.paused = false;
      listeners.get("play")?.forEach((fn) => fn(new Event("play")));
    }),
    pause: vi.fn(function (this: HTMLAudioElement) {
      this.paused = true;
    }),
    load: vi.fn(),
    addEventListener: vi.fn((type: string, fn: EventListener) => {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type)!.add(fn);
    }),
    removeEventListener: vi.fn((type: string, fn: EventListener) => {
      listeners.get(type)?.delete(fn);
    }),
    ...overrides,
  } as unknown as HTMLAudioElement;
  return el;
}

afterEach(() => {
  _resetAudioPlaybackRegistryForTests();
  vi.restoreAllMocks();
});

describe("audioPlayback", () => {
  it("registerExclusiveAudio pauses siblings on play", async () => {
    const a = mockAudio();
    const b = mockAudio();
    const unregA = registerExclusiveAudio(a);
    const unregB = registerExclusiveAudio(b);
    b.paused = false;

    await a.play();

    expect(b.pause).toHaveBeenCalled();
    unregA();
    unregB();
  });

  it("loadAndPlay sets src, waits when needed, and plays", async () => {
    const el = mockAudio({ readyState: 4 });
    await loadAndPlay(el, "/api/runs/r1/audio?path=a.wav");
    expect(el.src).toContain("a.wav");
    expect(el.play).toHaveBeenCalled();
    expect(el.currentTime).toBe(0);
  });

  it("togglePlayPause plays when paused and pauses when playing", async () => {
    const el = mockAudio({ paused: true });
    await expect(togglePlayPause(el)).resolves.toBe("play");
    el.paused = false;
    await expect(togglePlayPause(el)).resolves.toBe("pause");
    expect(el.pause).toHaveBeenCalled();
  });

  it("pauseOtherAudio pauses other registered players", () => {
    const a = mockAudio({ paused: false });
    const b = mockAudio({ paused: false });
    registerExclusiveAudio(a);
    registerExclusiveAudio(b);
    pauseOtherAudio(a);
    expect(b.pause).toHaveBeenCalled();
    expect(a.pause).not.toHaveBeenCalled();
  });
});
