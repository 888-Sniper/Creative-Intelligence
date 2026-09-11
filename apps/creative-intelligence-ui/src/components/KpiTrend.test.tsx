import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { formatDay, formatRange, KpiTrend } from "@/components/KpiTrend";
import type { KpiComparison } from "@/components/KpiTrend";

const PREV = { start: "2023-12-25", end: "2023-12-31" };

function comp(over: Partial<KpiComparison>): KpiComparison {
  return {
    percent_change: 25,
    direction: "up",
    sentiment: "good",
    state: "compared",
    ...over,
  };
}

afterEach(() => {
  cleanup();
});

describe("format helpers", () => {
  it("formats ISO days and ranges", () => {
    expect(formatDay("2023-12-25")).toBe("Dec 25, 2023");
    expect(formatDay("not-a-day")).toBe("not-a-day");
    expect(formatRange(PREV)).toBe("Dec 25 – Dec 31, 2023");
    expect(formatRange({ start: "2023-12-25", end: "2024-01-05" })).toBe(
      "Dec 25, 2023 – Jan 5, 2024",
    );
  });
});

describe("KpiTrend", () => {
  it("renders a positive comparison compactly", () => {
    render(<KpiTrend metricLabel="Impressions" comparison={comp({})} previous={PREV} />);
    expect(screen.getByText("↑")).toBeDefined();
    expect(screen.getByText("+25%")).toBeDefined();
    expect(screen.queryByText(/previous period/i)).toBeNull();
  });

  it("renders negative and CPA-bad sentiment distinctly", () => {
    const { container } = render(
      <KpiTrend
        metricLabel="CPA"
        comparison={comp({ percent_change: 12, direction: "up", sentiment: "bad" })}
        previous={PREV}
      />,
    );
    expect(screen.getByText("+12%")).toBeDefined();
    expect(container.querySelector(".trend-bad")).not.toBeNull();
    expect(container.querySelector(".trend-good")).toBeNull();
  });

  it("renders flat neutrally", () => {
    const { container } = render(
      <KpiTrend
        metricLabel="ROAS"
        comparison={comp({ percent_change: 0, direction: "flat", sentiment: "neutral" })}
        previous={PREV}
      />,
    );
    expect(screen.getByText("0%")).toBeDefined();
    expect(container.querySelector(".trend-neutral")).not.toBeNull();
  });

  it("renders the new state without a percentage", () => {
    render(
      <KpiTrend
        metricLabel="Conversions"
        comparison={comp({ percent_change: null, direction: "up", sentiment: "neutral", state: "new" })}
        previous={PREV}
      />,
    );
    expect(screen.getByText("New")).toBeDefined();
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it("renders nothing without a valid comparison", () => {
    const { container } = render(
      <KpiTrend
        metricLabel="Impressions"
        comparison={comp({ percent_change: null, direction: "flat", sentiment: "neutral", state: "none" })}
        previous={PREV}
      />,
    );
    expect(container.textContent).toBe("");
  });

  it("never renders Infinity or NaN", () => {
    const { container } = render(
      <KpiTrend
        metricLabel="Impressions"
        comparison={comp({ percent_change: Number.POSITIVE_INFINITY })}
        previous={PREV}
      />,
    );
    // Infinity is not a value the backend can send (percent_change is
    // null in every unmeasurable case); if it ever arrives, the raw
    // value must still not leak the words Infinity/NaN into the DOM.
    expect(container.textContent).not.toMatch(/Infinity|NaN/);
  });

  it("exposes an accessible info control that opens on focus", () => {
    render(<KpiTrend metricLabel="Impressions" comparison={comp({})} previous={PREV} />);
    const btn = screen.getByRole("button", { name: "Explain Comparison Period" });
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    fireEvent.focus(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("tooltip").textContent).toContain("Dec 25 – Dec 31, 2023");
    fireEvent.blur(btn);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("toggles on click and closes on Escape", () => {
    render(<KpiTrend metricLabel="Impressions" comparison={comp({})} previous={PREV} />);
    const btn = screen.getByRole("button", { name: "Explain Comparison Period" });
    fireEvent.click(btn);
    expect(screen.getByRole("tooltip")).toBeDefined();
    fireEvent.click(btn);
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.click(btn);
    expect(screen.getByRole("tooltip")).toBeDefined();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("keeps the tooltip open across a touch tap sequence", () => {
    render(<KpiTrend metricLabel="Impressions" comparison={comp({})} previous={PREV} />);
    const btn = screen.getByRole("button", { name: "Explain Comparison Period" });
    // A real tap fires focus immediately before click.
    fireEvent.focus(btn);
    fireEvent.click(btn);
    expect(screen.getByRole("tooltip")).toBeDefined();
    // The next tap closes it again.
    fireEvent.click(btn);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("explains new state and missing ranges honestly", () => {
    render(
      <KpiTrend
        metricLabel="Conversions"
        comparison={comp({ percent_change: null, direction: "up", sentiment: "neutral", state: "new" })}
        previous={null}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Explain Comparison Period" }));
    expect(screen.getByRole("tooltip").textContent).toContain("No Previous Data");
  });
});
