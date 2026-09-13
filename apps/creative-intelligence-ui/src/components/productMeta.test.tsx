import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";

afterEach(cleanup);
import {
  __resetCampaignMetaCache,
  refreshCampaignMeta,
  useCampaignMeta,
} from "@/components/product";

function Probe({ tag }: { tag: string }) {
  const meta = useCampaignMeta();
  return (
    <span data-testid={tag}>
      {(meta.data?.campaigns ?? []).map((c) => c.name).join(",") || "loading"}
    </span>
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

function metaBody(names: string[]) {
  return {
    campaigns: names.map((name) => ({
      name, client: "Acme", team: "Growth", platforms: ["meta"],
      markets: [], objectives: [], verticals: [], projects: [],
      last_date: "", status: "Active",
    })),
    demo: true,
  };
}

describe("useCampaignMeta broadcast", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetCampaignMetaCache();
  });

  it("refetches every mounted hook after refreshCampaignMeta", async () => {
    let calls = 0;
    window.fetch = vi.fn(async () => {
      calls += 1;
      return jsonResponse(metaBody(calls === 1 ? ["Camp A"] : ["Camp A", "Camp B"]));
    }) as unknown as typeof fetch;
    render(
      <>
        <Probe tag="one" />
        <Probe tag="two" />
      </>,
    );
    await waitFor(() => expect(screen.getByTestId("one").textContent).toBe("Camp A"));
    expect(screen.getByTestId("two").textContent).toBe("Camp A");
    expect(calls).toBe(1);
    // An admin demo op invalidates: both mounted hooks reload, one fetch.
    act(() => { refreshCampaignMeta(); });
    await waitFor(() => expect(screen.getByTestId("one").textContent).toBe("Camp A,Camp B"));
    expect(screen.getByTestId("two").textContent).toBe("Camp A,Camp B");
    expect(calls).toBe(2);
  });
});
