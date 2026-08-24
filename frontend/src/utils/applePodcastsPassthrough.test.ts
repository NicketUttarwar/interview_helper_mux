import { describe, expect, it } from "vitest";
import {
  APPLE_PODCASTS_CONNECT_NEW_FEED,
  applePodcastsPassthroughUrl,
  normalizePublicFeedUrl,
} from "./applePodcastsPassthrough";

describe("applePodcastsPassthroughUrl", () => {
  it("encodes an https feed into Apple's submitfeed pass-through", () => {
    const feed = "https://d111.cloudfront.net/feed.xml";
    const out = applePodcastsPassthroughUrl(feed);
    expect(out).toBe(
      `${APPLE_PODCASTS_CONNECT_NEW_FEED}?submitfeed=${encodeURIComponent(feed)}`,
    );
  });

  it("rejects non-http schemes, credentials, and whitespace", () => {
    expect(normalizePublicFeedUrl("")).toBeNull();
    expect(applePodcastsPassthroughUrl("javascript:alert(1)")).toBeNull();
    expect(applePodcastsPassthroughUrl("https://user:pass@evil.example/feed.xml")).toBeNull();
    expect(applePodcastsPassthroughUrl("https://d111.cloudfront.net/feed.xml\nhttps://evil")).toBeNull();
  });
});
