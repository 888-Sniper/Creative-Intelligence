import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FilterProvider, useFilters } from "./FilterContext";

// This test exercises only ordinary date-filter state, with unrelated boundaries simulated.
vi.mock("@/auth/AuthProvider", () => ({ useOptionalAuth: () => null }));
vi.mock("@/state/prefs", () => ({ markCampaignStatusTouched: () => {} }));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function Controls({ days }: { days: number }) {
  const { filters, setFilter, applyPresetDays } = useFilters();
  return <>
    <button onClick={() => setFilter("date", "2026-01-02")}>Exact date</button>
    <button onClick={() => applyPresetDays(days)}>Apply preset</button>
    <output>{JSON.stringify({ date: filters.date, from: filters.date_from, to: filters.date_to })}</output>
  </>;
}

describe("shared date preset state", () => {
  it.each([NaN, Infinity, 0, -1, 1.5, Number.MAX_SAFE_INTEGER])(
    "preserves an existing exact date for invalid input %s", (days) => {
      render(<FilterProvider><Controls days={days} /></FilterProvider>);
      fireEvent.click(screen.getByText("Exact date"));
      fireEvent.click(screen.getByText("Apply preset"));
      expect(screen.getByRole("status").textContent).toBe(JSON.stringify({ date: "2026-01-02", from: "", to: "" }));
    },
  );

  it("clears an exact date for a valid preset and preserves the window on a later invalid input", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-29T12:00:00Z"));
    const view = render(<FilterProvider><Controls days={7} /></FilterProvider>);
    fireEvent.click(screen.getByText("Exact date"));
    fireEvent.click(screen.getByText("Apply preset"));
    const expected = JSON.stringify({ date: "", from: "2026-10-23", to: "2026-10-29" });
    expect(screen.getByRole("status").textContent).toBe(expected);
    view.rerender(<FilterProvider><Controls days={NaN} /></FilterProvider>);
    fireEvent.click(screen.getByText("Apply preset"));
    fireEvent.click(screen.getByText("Apply preset"));
    expect(screen.getByRole("status").textContent).toBe(expected);
  });
});
