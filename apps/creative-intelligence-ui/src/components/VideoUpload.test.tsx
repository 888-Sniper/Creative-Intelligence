import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DashboardPage } from "@/pages/DashboardPage";
import { VideoUploadCard } from "@/components/VideoUploadCard";
import { VideoUploadPanel } from "@/components/VideoUploadPanel";
import { FilterProvider } from "@/state/FilterContext";
import type { DraftView } from "@/components/videoUploadApi";

vi.mock("@/auth/AuthProvider", () => ({
  useAuth: () => ({
    me: {
      employee: {
        id: "e7", email: "ada@foap.test", first_name: "Ada",
        last_name: "L", avatar_url: "", provider: "email", role: "employee",
        status: "active", created_at: "", approved_at: "", approved_by: "",
        last_login_at: "", updated_at: "",
      },
    },
  }),
}));

const comparePayload = {
  current_period: { start: "2026-07-01", end: "2026-07-30" },
  previous_period: { start: "2026-06-01", end: "2026-06-30" },
  comparison: "30d vs prior 30d",
  current_n_ads: 4,
  metrics: {
    impressions: { state: "compared", direction: "up", sentiment: "good", percent_change: 12, current: 5000000, previous: 4464000, abs_change: 536000 },
    clicks: { state: "compared", direction: "up", sentiment: "good", percent_change: 8, current: 120000, previous: 111000, abs_change: 9000 },
    spend: { state: "compared", direction: "up", sentiment: "neutral", percent_change: 5, current: 60000, previous: 57100, abs_change: 2900 },
    roas: { state: "compared", direction: "up", sentiment: "good", percent_change: 6, current: 3.4, previous: 3.2, abs_change: 0.2 },
  },
};

function dayPoints() {
  const out = [];
  for (let d = 1; d <= 30; d++) {
    const dd = String(d).padStart(2, "0");
    out.push({
      date: `2026-07-${dd}`, impressions: 1000, clicks: 20,
      spend: 50, conversions: 2, revenue: 170,
    });
  }
  return out;
}

function baseDraft(over: Partial<DraftView> = {}): DraftView {
  return {
    id: "d-new",
    owner_employee_id: "e7",
    status: "draft",
    dataset_version: "",
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    spec: {},
    videos: [],
    datasets: [],
    matches: [],
    live_job_id: "",
    ...over,
  };
}

const readyDraft: DraftView = baseDraft({
  id: "d1",
  dataset_version: "v1",
  updated_at: "2026-09-10T10:00:00Z",
  spec: {
    client: "Foap",
    campaign: "Sample Launch",
    clientConfirmed: true,
    creative_key: "video-upload-sample",
    platform: "meta",
    media: { id: 12, filename: "sample.mp4", bytes: 356681, sha256: "abc", url: "/media/12" },
    video: { video_id: "vid1", duration_s: 15, width: 1280, height: 720, status: "valid" },
    dataset: {
      dataset_id: "ds1", version: "v1", rows: 3, inserted: 3,
      updated: 0, quarantined: 0, filename: "data.csv",
      candidates: [
        { ad_name: "Sample Story V1", campaign: "Sample Launch", adset: "Prospecting AU", impressions: "1000", clicks: "25", creative_key: "video-upload-sample" },
      ],
    },
  },
});

interface FetchCall {
  method: string;
  url: string;
  body: unknown;
}

function mockBackend(matches: Array<(method: string, url: string, body: unknown) => unknown>) {
  const calls: FetchCall[] = [];
  const mock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method || "GET").toUpperCase();
    let body: unknown;
    const raw = init?.body;
    if (typeof raw === "string") {
      try {
        body = JSON.parse(raw) as unknown;
      } catch {
        body = raw;
      }
    } else if (raw instanceof FormData) {
      body = { __form: true };
    }
    calls.push({ method, url, body });
    for (const fn of matches) {
      const out = fn(method, url, body);
      if (out !== undefined) return Response.json(out);
    }
    return Response.json({});
  });
  window.fetch = mock as unknown as typeof fetch;
  return { calls };
}

function dashboardBackend(drafts: DraftView[]) {
  return mockBackend([
    (_m, u) => (u.startsWith("/api/kpis/compare") ? comparePayload : undefined),
    (_m, u) => (u.startsWith("/api/kpis/daily") ? { days: dayPoints() } : undefined),
    (m, u) => (u === "/api/drafts" && m === "GET" ? { drafts } : undefined),
    (_m, u) => (u.startsWith("/api/campaigns/meta") ? { campaigns: [], demo: false } : undefined),
    (_m, u) => (u.startsWith("/api/campaigns") ? {} : undefined),
    (_m, u) => (u.startsWith("/api/creatives") ? [] : undefined),
    (_m, u) => (u.startsWith("/api/benchmarks") ? {} : undefined),
    (_m, u) => (u.startsWith("/api/retention/curve") ? { points: [] } : undefined),
  ]);
}

function panelBackend(extra: Array<(method: string, url: string, body: unknown) => unknown> = []) {
  return mockBackend([
    ...extra,
    (m, u, b) => (u === "/api/drafts" && m === "POST"
      ? { draft: baseDraft({ id: "d-new", spec: ((b as Record<string, unknown>)?.["spec"] as DraftView["spec"]) ?? {} }) }
      : undefined),
    (m, u) => (u === "/api/drafts/d1" && m === "GET" ? { draft: readyDraft } : undefined),
    (m, u, b) => {
      if (u === "/api/drafts/d-new" && m === "PATCH") {
        const patch = (b ?? {}) as { status?: string; spec?: DraftView["spec"] };
        return {
          draft: baseDraft({
            id: "d-new", status: patch.status ?? "draft", spec: patch.spec ?? {},
          }),
        };
      }
      return undefined;
    },
    (m, u, b) => {
      if (u === "/api/drafts/d1" && m === "PATCH") {
        const patch = (b ?? {}) as { status?: string; spec?: DraftView["spec"] };
        return {
          draft: {
            ...readyDraft,
            status: patch.status ?? readyDraft.status,
            spec: patch.spec ?? readyDraft.spec,
          },
        };
      }
      return undefined;
    },
    (m, u) => (u === "/api/videos/limits" && m === "GET"
      ? { containers: [".mp4", ".mov"], max_bytes: 104857600, max_duration_s: 300, note: "x" }
      : undefined),
    (_m, u) => (u.startsWith("/api/campaigns/meta") ? { campaigns: [], demo: false } : undefined),
    (m, u) => (u === "/api/drafts/d1/matches/confirm" && m === "POST"
      ? {
        match: {
          draft_id: "d1", creative_key: "video-upload-sample", method: "manual",
          record_json: JSON.stringify([
            { id: 11, import_id: "v1", ad_name: "Sample Story V1", campaign: "Sample Launch" },
            { id: 12, import_id: "v1", ad_name: "Sample Story V1", campaign: "Sample Launch" },
          ]),
          confirmed: 1, confirmed_by: "e7", confirmed_at: "2026-09-10T11:00:00Z",
        },
      }
      : undefined),
  ]);
}

/** This jsdom setup ships without localStorage (see sync.test.tsx):
 *  install the same in-memory double so recovery pins behave. */
function installStorage(): void {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    value: {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => { store.set(k, String(v)); },
      removeItem: (k: string) => { store.delete(k); },
      clear: () => { store.clear(); },
    },
    configurable: true,
  });
}

describe("VideoUpload dashboard card", () => {
  beforeEach(() => {
    installStorage();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("places the card between the greeting and the filters", async () => {
    dashboardBackend([]);
    render(
      <MemoryRouter>
        <FilterProvider>
          <DashboardPage />
        </FilterProvider>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Analyze a video" })).toBeDefined();
    });
    const greeting = screen.getByRole("heading", { level: 1 });
    const card = screen.getByRole("heading", { name: "Analyze a video" });
    const filters = screen.getByLabelText("Filters");
    const follows = (a: Element, b: Element): boolean =>
      Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(follows(greeting, card)).toBe(true);
    expect(follows(card, filters)).toBe(true);
    expect(screen.getByRole("button", { name: /Upload video/ })).toBeDefined();
  });

  it("lists recent drafts with status text plus actions", async () => {
    dashboardBackend([readyDraft]);
    render(
      <MemoryRouter>
        <FilterProvider>
          <DashboardPage />
        </FilterProvider>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Recent uploads")).toBeDefined();
    });
    // Status is text (never color-only) with per-status actions.
    expect(screen.getByText("Draft")).toBeDefined();
    expect(screen.getByText("sample.mp4")).toBeDefined();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDefined();
  });

  it("recovers a pinned draft from localStorage", async () => {
    window.localStorage.setItem("ci-video-draft:e7", "d1");
    panelBackend([
      (m, u) => (u === "/api/drafts" && m === "GET" ? { drafts: [readyDraft] } : undefined),
    ]);
    render(
      <MemoryRouter>
        <VideoUploadCard />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText(/Unfinished upload/)).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Resume" }));
    // Recovery opens the panel on the furthest stage (review here).
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review and analyze" })).toBeDefined();
    });
    expect(screen.getByText(/3 records|No match confirmed yet/)).toBeDefined();
  });

  it("renders the same card copy under light and dark themes", async () => {
    for (const theme of ["light", "dark"]) {
      document.documentElement.setAttribute("data-theme", theme);
      dashboardBackend([readyDraft]);
      render(
        <MemoryRouter>
          <VideoUploadCard />
        </MemoryRouter>,
      );
      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Analyze a video" })).toBeDefined();
      });
      expect(screen.getByRole("button", { name: /Upload video/ })).toBeDefined();
      // Status stays a text pill in both themes (never color-only).
      expect(screen.getByText("Draft")).toBeDefined();
      cleanup();
      window.localStorage.clear();
    }
  });
});

describe("VideoUpload guided panel", () => {
  beforeEach(() => {
    installStorage();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  function openPanel() {
    panelBackend();
    render(
      <MemoryRouter>
        <VideoUploadPanel open={{}} employeeId="e7" onClose={() => undefined} />
      </MemoryRouter>,
    );
  }

  it("navigates all four stages with Back and Continue", async () => {
    openPanel();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Upload your video" })).toBeDefined();
    });
    // Real limits text comes from GET /api/videos/limits.
    expect(screen.getByText(".MP4 / .MOV only · up to 100 MB · up to 300s")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("heading", { name: "Client and campaign" })).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("heading", { name: "Performance dataset" })).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("heading", { name: "Review and analyze" })).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("heading", { name: "Performance dataset" })).toBeDefined();
  });

  it("pins the new draft id for recovery and saves spec on Save draft", async () => {
    const { calls } = panelBackend();
    render(
      <MemoryRouter>
        <VideoUploadPanel open={{}} employeeId="e7" onClose={() => undefined} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Upload your video" })).toBeDefined();
    });
    expect(window.localStorage.getItem("ci-video-draft:e7")).toBe("d-new");
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => {
      // Announced twice by design: the polite status region + the toast.
      expect(screen.getAllByText("Draft saved.").length).toBeGreaterThanOrEqual(1);
    });
    const patch = calls.find((c) => c.method === "PATCH" && c.url === "/api/drafts/d-new");
    expect(patch).toBeDefined();
    expect((patch?.body as Record<string, unknown>)?.["spec"]).toBeDefined();
  });

  it("uploads a video and shows preview, duration and size", async () => {
    panelBackend([
      (m, u) => (u === "/api/media/upload" && m === "POST"
        ? { id: 12, creative_key: "video-upload-sample", filename: "sample.mp4", mime: "video/mp4", bytes: 356681, sha256: "abc", created_at: "x", url: "/media/12" }
        : undefined),
      (m, u) => (u === "/api/videos/validate" && m === "POST"
        ? { video_id: "vid1", media_id: 12, creative_key: "video-upload-sample", duration_s: 15, width: 1280, height: 720, validation: { status: "valid", duration_s: 15, width: 1280, height: 720 } }
        : undefined),
      (m, u, b) => {
        if (u === "/api/drafts/d-new" && m === "PATCH") {
          const patch = (b ?? {}) as { spec?: DraftView["spec"] };
          return { draft: baseDraft({ spec: patch.spec ?? {} }) };
        }
        return undefined;
      },
    ]);
    render(
      <MemoryRouter>
        <VideoUploadPanel open={{}} employeeId="e7" onClose={() => undefined} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByLabelText("Video file")).toBeDefined();
    });
    const file = new File(["fake-bytes"], "sample.mp4", { type: "video/mp4" });
    fireEvent.change(screen.getByLabelText("Video file"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload video" }));
    await waitFor(() => {
      expect(screen.getByText("Video valid — 1280×720, 15s.")).toBeDefined();
    });
    expect(screen.getByTestId("vu-video-preview")).toBeDefined();
    expect(screen.getByText("348.3 KB")).toBeDefined();
  });

  it("keeps Analyze disabled without a video or a match, with reason text", async () => {
    openPanel();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Upload your video" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    const analyze = screen.getByRole("button", { name: "Analyze" });
    expect(analyze.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Add and validate a video to enable analysis.")).toBeDefined();
  });

  it("keeps Analyze disabled with a valid video but no confirmed match", async () => {
    window.localStorage.setItem("ci-video-draft:e7", "d1");
    panelBackend();
    render(
      <MemoryRouter>
        <VideoUploadPanel open={{ draftId: "d1", stage: "review" }} employeeId="e7" onClose={() => undefined} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review and analyze" })).toBeDefined();
    });
    const analyze = screen.getByRole("button", { name: "Analyze" });
    expect(analyze.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Confirm the dataset match to enable analysis.")).toBeDefined();
  });

  it("confirms the match and queues analysis via the analyze endpoint", async () => {
    window.localStorage.setItem("ci-video-draft:e7", "d1");
    const { calls } = panelBackend([
      (m, u) => (u === "/api/drafts/d1/candidates" && m === "GET"
        ? {
          version: "v1",
          candidates: [
            { id: 11, import_id: "v1", ad_name: "Sample Story V1", campaign: "Sample Launch" },
            { id: 12, import_id: "v1", ad_name: "Sample Story V1", campaign: "Sample Launch" },
          ],
        }
        : undefined),
      (m, u) => (u === "/api/drafts/d1/analyze" && m === "POST"
        ? {
          job_id: "job-1", status: "analyzing", draft_id: "d1",
          model: "gemini/gemini-2.5-flash", provider: "gemini",
          sends: "frames", storage: "private", poll: "/api/pipeline/jobs/job-1",
        }
        : undefined),
    ]);
    render(
      <MemoryRouter>
        <VideoUploadPanel open={{ draftId: "d1", stage: "review" }} employeeId="e7" onClose={() => undefined} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Confirm match" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm match" }));
    await waitFor(() => {
      expect(screen.getByText("Match confirmed.")).toBeDefined();
    });
    const confirm = calls.find((c) => c.url === "/api/drafts/d1/matches/confirm");
    expect((confirm?.body as Record<string, unknown>)?.["ad_rowids"]).toEqual([11, 12]);
    const analyze = screen.getByRole("button", { name: "Analyze" });
    expect(analyze.hasAttribute("disabled")).toBe(false);
    fireEvent.click(analyze);
    await waitFor(() => {
      const queued = calls.find((c) =>
        c.method === "POST" && c.url === "/api/drafts/d1/analyze");
      expect(queued).toBeDefined();
    });
    expect(window.localStorage.getItem("ci-video-draft:e7")).toBeNull();
  });

  it("renders finished findings with measured numbers and hypotheses", async () => {
    const reviewed = baseDraft({
      id: "d2", status: "ready_for_review", dataset_version: "v1",
      spec: {
        creative_key: "video-upload-sample",
        video: { video_id: "vid1", duration_s: 15, width: 1280, height: 720, status: "valid" },
        dataset: { dataset_id: "ds1", version: "v1", rows: 3, inserted: 3, updated: 0, quarantined: 0, filename: "data.csv" },
        match: { method: "platform_id", adRowIds: [11], matchedCount: 1, confirmed: true },
      },
      matches: [
        {
          draft_id: "d2", creative_key: "video-upload-sample", method: "platform_id",
          record_json: JSON.stringify([{ id: 11 }]),
          confirmed: 1, confirmed_by: "e7", confirmed_at: "2026-09-10T11:00:00Z",
        },
      ],
    });
    panelBackend([
      (m, u) => (u === "/api/drafts/d2" && m === "GET" ? { draft: reviewed } : undefined),
      (m, u) => (u === "/api/drafts/d2/candidates" && m === "GET"
        ? { version: "v1", candidates: [{ id: 11, import_id: "v1" }] }
        : undefined),
      (m, u) => (u === "/api/drafts/d2/analysis" && m === "GET"
        ? {
          draft_id: "d2", status: "ready_for_review",
          creative_key: "video-upload-sample", transcript: "watch this",
          annotation: {
            status: "auto",
            analysis: {
              version: "v1", at: "2026-09-10T12:00:00Z",
              model: "gemini/gemini-2.5-flash",
              measured: {
                totals: { impressions: 6000, link_clicks: 150 },
                pooled_link_ctr_pct: 2.5, warnings: [],
              },
              suggested_tests: [
                { id: "cta-presence", hypothesis: "Test an explicit CTA.", why: "no CTA seen", status: "suggested" },
              ],
            },
          },
        }
        : undefined),
    ]);
    render(
      <MemoryRouter>
        <VideoUploadPanel open={{ draftId: "d2", stage: "review" }} employeeId="e7" onClose={() => undefined} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Findings" })).toBeDefined();
    });
    expect(screen.getByText("6000 impressions · 150 link clicks · pooled CTR 2.5%.")).toBeDefined();
    expect(screen.getByText("Test an explicit CTA.")).toBeDefined();
    expect(screen.getByText("watch this")).toBeDefined();
  });
});
