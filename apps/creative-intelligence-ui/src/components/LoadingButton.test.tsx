import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { LoadingButton } from "@/components/LoadingButton";

afterEach(() => {
  cleanup();
});

describe("LoadingButton", () => {
  it("renders idle children without a spinner", () => {
    render(
      <LoadingButton type="button" loading={false} loadingLabel="Saving…">
        Save Insight
      </LoadingButton>,
    );
    const btn = screen.getByRole("button", { name: "Save Insight" });
    expect(btn.getAttribute("disabled")).toBeNull();
    expect(btn.getAttribute("aria-busy")).toBe("false");
    expect(btn.querySelector(".spinner")).toBeNull();
  });

  it("shows only its own spinner and label while loading", () => {
    let clicks = 0;
    render(
      <LoadingButton type="button" loading loadingLabel="Preparing…" onClick={() => { clicks += 1; }}>
        Report
      </LoadingButton>,
    );
    const btn = screen.getByRole("button", { name: "Preparing…" });
    expect(btn.querySelector(".spinner")).not.toBeNull();
    expect(btn.getAttribute("aria-busy")).toBe("true");
    // Disabled while loading: no double submit.
    fireEvent.click(btn);
    expect(clicks).toBe(0);
  });

  it("honours an explicit disabled flag when idle", () => {
    render(
      <LoadingButton type="button" loading={false} loadingLabel="Saving…" disabled>
        Save Insight
      </LoadingButton>,
    );
    expect(screen.getByRole("button", { name: "Save Insight" }).getAttribute("disabled")).not.toBeNull();
  });
});
