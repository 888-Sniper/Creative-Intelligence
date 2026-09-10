import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { kindForUrl, MediaPreview } from "@/components/MediaPreview";

describe("kindForUrl", () => {
  it("prefers the exact mime over the URL", () => {
    expect(kindForUrl("/media/7", "audio/mpeg")).toBe("audio");
    expect(kindForUrl("https://x/v.mp4", "image/png")).toBe("image");
    expect(kindForUrl("https://x/v.mp4", "video/mp4")).toBe("video");
  });

  it("sniffs remote extensions", () => {
    expect(kindForUrl("https://x/clip.mp4")).toBe("video");
    expect(kindForUrl("https://x/song.mp3")).toBe("audio");
    expect(kindForUrl("https://x/shot.png")).toBe("image");
  });

  it("falls back to video for unknown URLs", () => {
    expect(kindForUrl("https://x/blob")).toBe("video");
  });
});

describe("MediaPreview", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  function mockMedia(mime: string) {
    window.fetch = vi.fn(async () =>
      Response.json({ media: [{ url: "/media/7", mime }] }),
    ) as unknown as typeof fetch;
  }

  it("renders video for remote mp4 without fetching", async () => {
    const seen: string[] = [];
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      seen.push(String(input));
      return Response.json({});
    }) as unknown as typeof fetch;
    render(<MediaPreview src="https://x/clip.mp4" creativeKey="ck1" testId="pv" />);
    await waitFor(() => {
      expect(screen.getByTestId("pv").tagName).toBe("VIDEO");
    });
    expect(seen).toEqual([]);
  });

  it("renders audio for remote mp3", async () => {
    window.fetch = vi.fn(async () => Response.json({})) as unknown as typeof fetch;
    render(<MediaPreview src="https://x/song.mp3" creativeKey="ck1" testId="pa" />);
    await waitFor(() => {
      expect(screen.getByTestId("pa").tagName).toBe("AUDIO");
    });
  });

  it("renders img for remote png", async () => {
    window.fetch = vi.fn(async () => Response.json({})) as unknown as typeof fetch;
    render(<MediaPreview src="https://x/shot.png" creativeKey="ck1" testId="pi" />);
    await waitFor(() => {
      expect(screen.getByTestId("pi").tagName).toBe("IMG");
    });
  });

  it("resolves numeric media mime from by-creative", async () => {
    mockMedia("audio/mpeg");
    render(<MediaPreview src="/media/7" creativeKey="ck1" testId="pm" />);
    await waitFor(() => {
      expect(screen.getByTestId("pm").tagName).toBe("AUDIO");
    });
  });
});
