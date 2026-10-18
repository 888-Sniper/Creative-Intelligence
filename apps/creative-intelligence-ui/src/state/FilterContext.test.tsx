import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";

afterEach(cleanup);
import { FilterProvider, useFilters } from "@/state/FilterContext";
import {
  markCampaignStatusTouched,
  touchedCampaignStatus,
} from "@/state/prefs";

function Probe() {
  const { filters, setFilter, clearFilters } = useFilters();
  return (
    <div>
      <span data-testid="date">{filters.date}</span>
      <span data-testid="from">{filters.date_from}</span>
      <span data-testid="to">{filters.date_to}</span>
      <span data-testid="status">{filters.status}</span>
      <button type="button" onClick={() => setFilter("date_from", "2024-01-01")}>
        set-from
      </button>
      <button type="button" onClick={() => setFilter("date_to", "2024-01-07")}>
        set-to
      </button>
      <button type="button" onClick={() => setFilter("date", "2024-01-07")}>
        set-date
      </button>
      <button type="button" onClick={() => setFilter("status", "Completed")}>
        set-status
      </button>
      <button type="button" onClick={clearFilters}>
        clear
      </button>
    </div>
  );
}

function renderProbe() {
  render(
    <FilterProvider>
      <Probe />
    </FilterProvider>,
  );
}

describe("exact Date vs From/To mutual exclusivity", () => {
  it("entering Date clears From/To", () => {
    renderProbe();
    act(() => {
      screen.getByRole("button", { name: "set-from" }).click();
      screen.getByRole("button", { name: "set-to" }).click();
    });
    expect(screen.getByTestId("from").textContent).toBe("2024-01-01");
    act(() => {
      screen.getByRole("button", { name: "set-date" }).click();
    });
    expect(screen.getByTestId("date").textContent).toBe("2024-01-07");
    expect(screen.getByTestId("from").textContent).toBe("");
    expect(screen.getByTestId("to").textContent).toBe("");
  });

  it("entering From or To clears Date", () => {
    renderProbe();
    act(() => {
      screen.getByRole("button", { name: "set-date" }).click();
    });
    expect(screen.getByTestId("date").textContent).toBe("2024-01-07");
    act(() => {
      screen.getByRole("button", { name: "set-from" }).click();
    });
    expect(screen.getByTestId("date").textContent).toBe("");
    expect(screen.getByTestId("from").textContent).toBe("2024-01-01");
  });
});

describe("clearFilters records the explicit All status choice", () => {
  it("a remembered Completed status does not survive a clear", () => {
    // No AuthProvider here: the account key is "" (same key the
    // provider falls back to before identity loads).
    markCampaignStatusTouched("", "Completed");
    renderProbe();
    act(() => {
      screen.getByRole("button", { name: "set-status" }).click();
    });
    expect(screen.getByTestId("status").textContent).toBe("Completed");
    act(() => {
      screen.getByRole("button", { name: "clear" }).click();
    });
    expect(screen.getByTestId("status").textContent).toBe("");
    // Touched-with-no-value: Campaigns must show All on return,
    // not resurrect Completed from the remembered choice.
    expect(touchedCampaignStatus("")).toBe("");
  });
});
