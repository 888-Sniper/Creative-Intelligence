import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";

afterEach(cleanup);
import { FilterProvider, useFilters } from "@/state/FilterContext";

function Probe() {
  const { filters, setFilter } = useFilters();
  return (
    <div>
      <span data-testid="date">{filters.date}</span>
      <span data-testid="from">{filters.date_from}</span>
      <span data-testid="to">{filters.date_to}</span>
      <button type="button" onClick={() => setFilter("date_from", "2024-01-01")}>
        set-from
      </button>
      <button type="button" onClick={() => setFilter("date_to", "2024-01-07")}>
        set-to
      </button>
      <button type="button" onClick={() => setFilter("date", "2024-01-07")}>
        set-date
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
