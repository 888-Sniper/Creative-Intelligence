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
    // The loading face stays mounted (hidden) to reserve button width,
    // so assert no VISIBLE spinner rather than no spinner node.
    expect(btn.querySelector(".spinner")?.closest('[aria-hidden="true"]')).not.toBeNull();
    expect(btn.querySelector(".lb-face:not([aria-hidden]) .spinner")).toBeNull();
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

  it("reserves width for both labels so loading never shrinks the button", () => {
    render(
      <LoadingButton type="button" loading loadingLabel="Generating…">
        Generate Report
      </LoadingButton>,
    );
    const btn = screen.getByRole("button", { name: "Generating…" });
    // The hidden idle label stays in layout to hold the button width.
    expect(btn.textContent).toContain("Generate Report");
    expect(btn.querySelector('.lb-face[aria-hidden="true"]')).not.toBeNull();
    expect(btn.querySelector(".spinner")).not.toBeNull();
  });

  it("keeps the same button element across the loading swap", () => {
    // Dimension stability starts here: the swap must not remount the
    // button (which would drop focus and reset layout). The fixed-size
    // .spinner and inline-flex button styles hold the box steady.
    const { rerender } = render(
      <LoadingButton type="button" loading={false} loadingLabel="Saving…">
        Save Insight
      </LoadingButton>,
    );
    const before = screen.getByRole("button", { name: "Save Insight" });
    before.focus();
    rerender(
      <LoadingButton type="button" loading loadingLabel="Saving…">
        Save Insight
      </LoadingButton>,
    );
    const during = screen.getByRole("button");
    expect(during).toBe(before);
    expect(document.activeElement).toBe(before);
    expect(during.querySelector(".spinner")).not.toBeNull();
  });
});
