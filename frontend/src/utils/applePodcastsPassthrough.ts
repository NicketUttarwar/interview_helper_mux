/**
 * Apple Podcasts Connect pass-through for a public RSS feed URL.
 *
 * Apple's documented add-show form:
 *   https://podcastsconnect.apple.com/my-podcasts/new-feed?submitfeed=<feed>
 *
 * Only https/http public URLs are accepted. `submitfeed` is encoded so the
 * href cannot inject extra query params. Apple still requires ≥1 episode.
 */

export const APPLE_PODCASTS_CONNECT_NEW_FEED =
  "https://podcastsconnect.apple.com/my-podcasts/new-feed";

export const APPLE_PODCASTS_PASSTHROUGH_NOTICE =
  "Apple Podcasts Connect rejects an empty seed feed (no episodes). Publish at least one episode or a trailer, then open the pass-through URL. It only pre-fills the RSS field; it does not skip validation.";

export function normalizePublicFeedUrl(feedUrl: string | null | undefined): string | null {
  const text = String(feedUrl || "").trim();
  if (!text) return null;
  if (/[\s"'<>\\]/.test(text)) return null;
  let parsed: URL;
  try {
    parsed = new URL(text);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return null;
  if (parsed.username || parsed.password) return null;
  return text;
}

/** Safe href / copy-paste pass-through, or null if the feed URL is not public http(s). */
export function applePodcastsPassthroughUrl(feedUrl: string | null | undefined): string | null {
  const feed = normalizePublicFeedUrl(feedUrl);
  if (!feed) return null;
  return `${APPLE_PODCASTS_CONNECT_NEW_FEED}?submitfeed=${encodeURIComponent(feed)}`;
}
