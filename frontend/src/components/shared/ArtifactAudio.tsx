import { useEffect, useRef, type AudioHTMLAttributes } from "react";
import { registerExclusiveAudio } from "../../utils/audioPlayback";

type Props = AudioHTMLAttributes<HTMLAudioElement> & {
  /** When set, reloads the element when the identity changes (e.g. clip id). */
  reloadKey?: string | number;
};

/**
 * Shared run-artifact `<audio controls>` with exclusive playback
 * (starting this player pauses other GUI audio).
 */
export function ArtifactAudio({
  className = "",
  preload = "metadata",
  reloadKey,
  src,
  ...rest
}: Props) {
  const ref = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    return registerExclusiveAudio(el);
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el || reloadKey === undefined) return;
    el.load();
  }, [reloadKey, src]);

  return (
    <audio
      ref={ref}
      controls
      preload={preload}
      className={["audio-player", className].filter(Boolean).join(" ")}
      src={src}
      {...rest}
    />
  );
}
