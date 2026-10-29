import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { AnalystDateRangeSelect } from "./AnalystDateRangeSelect";

afterEach(cleanup);
const t = (key: string) => key;

describe("Analyst date preset selection", () => {
  it.each(["all", "7"])("does not offer Custom Range from %s", (value) => {
    const onChange = vi.fn();
    render(<AnalystDateRangeSelect value={value} onChange={onChange} t={t} />);
    const custom = screen.getByRole("option", { name: "analyst.ranges.custom" }) as HTMLOptionElement;
    expect(custom.disabled).toBe(true);
    // Even a synthetic change bypassing native disabled-option behavior is ignored.
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "custom" } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("displays a restored custom window, then accepts repeated valid selections", () => {
    const onChange = vi.fn();
    const view = render(<AnalystDateRangeSelect value="custom" onChange={onChange} t={t} />);
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("custom");
    for (const value of ["7", "30", "90", "all", "7"]) {
      fireEvent.change(screen.getByRole("combobox"), { target: { value } });
      expect(onChange).toHaveBeenLastCalledWith(value);
      view.rerender(<AnalystDateRangeSelect value={value} onChange={onChange} t={t} />);
      expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe(value);
    }
    expect(onChange).toHaveBeenCalledTimes(5);
    view.unmount();
    render(<AnalystDateRangeSelect value="custom" onChange={onChange} t={t} />);
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("custom");
    expect(onChange).toHaveBeenCalledTimes(5);
  });

  it("ignores values outside the offered presets", () => {
    const onChange = vi.fn();
    render(<AnalystDateRangeSelect value="all" onChange={onChange} t={t} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "invalid" } });
    expect(onChange).not.toHaveBeenCalled();
  });
});
