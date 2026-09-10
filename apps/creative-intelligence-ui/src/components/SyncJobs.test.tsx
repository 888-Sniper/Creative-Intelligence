import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SyncJobs, displayParams } from "@/components/SyncJobs";

const job = {
  id: "job-1", source: "meta", name: "Meta Account A",
  params: { account_id: "111", access_token: "sekret" },
  owner_employee_id: "emp-9", enabled: true,
  created_at: "2026-01-01", updated_at: "2026-01-02",
  last_run: {
    last_run_at: "2026-01-03", last_finished_at: "2026-01-03",
    last_status: "ok", last_inserted: 5, last_updated: 2, last_error: "",
  },
};

describe("displayParams", () => {
  it("masks secret-shaped values", () => {
    expect(displayParams({ account_id: "111", access_token: "sekret", apiKey: "k" })).toEqual({
      account_id: "111",
      access_token: "•••",
      apiKey: "•••",
    });
  });
});

describe("SyncJobs (item 26)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  function mockJobs(calls: Array<{ method: string; url: string; body: string }>, jobs = [job]) {
    window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      calls.push({ method: init?.method ?? "GET", url: String(input), body: String(init?.body ?? "") });
      return Response.json({ jobs });
    }) as unknown as typeof fetch;
  }

  it("lists jobs with history and masked params", async () => {
    const calls: Array<{ method: string; url: string; body: string }> = [];
    mockJobs(calls);
    render(<SyncJobs />);
    await waitFor(() => {
      expect(screen.getByText("Meta Account A")).toBeDefined();
    });
    expect(screen.getByText("emp-9")).toBeDefined();
    expect(screen.getByText(/ok @ 2026-01-03/)).toBeDefined();
    expect(screen.queryByText(/sekret/)).toBeNull();
  });

  it("creates a job from the form", async () => {
    const calls: Array<{ method: string; url: string; body: string }> = [];
    mockJobs(calls, []);
    render(<SyncJobs />);
    await waitFor(() => {
      expect(screen.getByText("No scheduled jobs yet — create one below.")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("New job name"), { target: { value: "TikTok B" } });
    fireEvent.click(screen.getByRole("button", { name: "Create job" }));
    await waitFor(() => {
      const post = calls.find((c) => c.method === "POST" && c.url === "/api/sync/jobs");
      expect(post).toBeDefined();
      expect(JSON.parse(post?.body ?? "{}").name).toBe("TikTok B");
    });
  });

  it("runs, toggles and deletes with confirmation", async () => {
    const calls: Array<{ method: string; url: string; body: string }> = [];
    mockJobs(calls);
    const asked: string[] = [];
    window.confirm = vi.fn((message?: string) => {
      asked.push(message ?? "");
      return true;
    });
    render(<SyncJobs />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Run now" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Run now" }));
    fireEvent.click(screen.getByRole("button", { name: "Disable" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => {
      expect(calls.some((c) => c.url === "/api/sync/jobs/job-1/run")).toBe(true);
      expect(
        calls.some((c) => c.method === "PATCH" && JSON.parse(c.body || "{}").enabled === false),
      ).toBe(true);
      expect(calls.some((c) => c.method === "DELETE")).toBe(true);
    });
    expect(asked.length).toBe(1);
  });
});
