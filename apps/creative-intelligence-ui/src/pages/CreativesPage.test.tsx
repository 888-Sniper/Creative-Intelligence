import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FilterProvider } from "@/state/FilterContext";
import { CreativesPage } from "@/pages/CreativesPage";

const rows = [
  {
    creative_key: "ck-alpha",
    name: "Alpha",
    platform: "meta",
    campaigns: ["Camp A"],
    duration_s: 30,
    metrics: { spend: 100, cpa: 2.5, ctr: 0.02, cpc: 0.5, cpm: 5, vtr: 0.4, roas: 3 },
    annotation: {
      hook_type: "question",
      hook_modality: "spoken",
      creator_vs_branded: "creator",
      edit_style: "fast",
      duration_s: 30,
      status: "human_verified",
      source_url: "/media/alpha.mp4",
      structure: { hook: { start_s: 0, end_s: 3 }, cta: { start_s: 25, end_s: 30 } },
      brand_seconds: [{ start_s: 2, end_s: 3 }],
      product_seconds: [{ start_s: 5, end_s: 7 }],
      pace_cuts_per_min: 12,
    },
  },
  {
    creative_key: "ck-beta",
    name: "Beta",
    platform: "tiktok",
    campaigns: ["Camp B"],
    duration_s: 15,
    metrics: { spend: 50, cpa: 5, ctr: 0.01, cpc: 1, cpm: 6, vtr: 0.3, roas: 1.5 },
    annotation: {
      hook_type: "offer",
      creator_vs_branded: "branded",
      edit_style: "slow",
      duration_s: 15,
      status: "auto",
    },
  },
];

const curve = {
  points: [
    { t: 0, p: 100 },
    { t: 10, p: 80 },
  ],
  markers: {},
};

function mockFetch(handler: (url: string) => { body: unknown; status?: number }) {
  window.fetch = vi.fn(async (input: unknown) => {
    const url = String(input);
    const { body, status } = handler(url);
    return Response.json(body, status ? { status } : undefined);
  }) as unknown as typeof fetch;
}

function mockLibrary() {
  mockFetch((url) => {
    if (url.startsWith("/api/creatives")) return { body: rows };
    if (url.startsWith("/api/retention/curve")) return { body: curve };
    if (url.startsWith("/api/retention/patterns")) return { body: { events: [] } };
    if (url.startsWith("/api/retention")) return { body: [] };
    return { body: {} };
  });
}

function renderPage() {
  return render(
    <FilterProvider>
      <CreativesPage />
    </FilterProvider>,
  );
}

describe("CreativesPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the library with mocked data", async () => {
    mockLibrary();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Alpha")).toBeDefined();
    });
    expect(screen.getByText("Beta")).toBeDefined();
    expect(screen.getByText("HUMAN-VERIFIED")).toBeDefined();
    expect(screen.getByText("Auto")).toBeDefined();
    expect(document.getElementById("creative-detail")).not.toBeNull();
    expect(screen.getByText("Select A Creative Below.")).toBeDefined();
  });

  it("shows a loading state while fetching", () => {
    window.fetch = vi.fn(
      () => new Promise<Response>(() => undefined),
    ) as unknown as typeof fetch;
    renderPage();
    expect(screen.getByText("Loading Creatives…")).toBeDefined();
  });

  it("renders fetch errors", async () => {
    mockFetch(() => ({ body: { error: "boom" }, status: 500 }));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("boom")).toBeDefined();
    });
  });

  it("selects a creative, seeks from a chip, and follows the playhead", async () => {
    mockLibrary();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Alpha")).toBeDefined();
    });
    fireEvent.click(screen.getByLabelText("Select Alpha"));
    const video = (await screen.findByTestId("creative-video")) as HTMLVideoElement;
    await waitFor(() => {
      expect(document.getElementById("retention-svg")).not.toBeNull();
    });
    // Click-to-seek still works: hook chip seeks the video to 0s.
    let sought: number | null = null;
    Object.defineProperty(video, "currentTime", {
      configurable: true,
      get: () => 0,
      set: (v: number) => {
        sought = v;
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Hook @ 0s" }));
    expect(sought).toBe(0);
    // Reverse sync: a video timeupdate moves the retention playhead.
    fireEvent.timeUpdate(video);
    const head = document.getElementById("retention-playhead");
    expect(head).not.toBeNull();
    expect(head?.getAttribute("x1")).toBe("44");
    expect((head as unknown as SVGLineElement).style.visibility).toBe("visible");
    expect(document.getElementById("retention-playhead-label")?.textContent).toBe("0.0s · 100%");
  });
});
