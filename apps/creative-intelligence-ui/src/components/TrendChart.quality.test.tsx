import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { TrendChart, type TrendSeries } from "./charts";

vi.mock("@/i18n", () => ({ useLocale: () => ({ locale: "en", t: (key: string) => key }) }));
afterEach(cleanup);

function series(points: ReadonlyArray<number | null>, extra: Partial<TrendSeries> = {}): TrendSeries {
  return { label: "ROAS", color: "#123456", soft: "#abcdef", points, ...extra };
}

function coordinate(mark: Element, name: string): number {
  return Number(mark.getAttribute(name));
}

describe("visible isolated trend observations", () => {
  it("draws one observation with a visible radius and the series color", () => {
    const view = render(<TrendChart series={[series([2])]} labels={["Monday"]} />);
    const marks = view.container.querySelectorAll("circle");
    expect(marks).toHaveLength(1);
    expect(coordinate(marks[0], "cx")).toBe(4);
    expect(coordinate(marks[0], "cy")).toBe(14);
    expect(coordinate(marks[0], "r")).toBeGreaterThanOrEqual(3);
    expect(marks[0].getAttribute("fill")).toBe("#123456");
  });

  it("keeps a middle observation at its original index between gaps", () => {
    const view = render(<TrendChart series={[series([null, 2, null])]} labels={["Mon", "Tue", "Wed"]} />);
    const marks = view.container.querySelectorAll("circle");
    expect(marks).toHaveLength(1);
    expect(coordinate(marks[0], "cx")).toBe(320);
    expect(coordinate(marks[0], "cy")).toBe(14);
    expect(view.container.querySelectorAll("path")).toHaveLength(0);
  });

  it("draws separated singletons without an area or connecting stroke", () => {
    const view = render(<TrendChart series={[series([1, null, 2])]} labels={["Mon", "Tue", "Wed"]} />);
    const marks = [...view.container.querySelectorAll("circle")];
    expect(marks).toHaveLength(2);
    expect(marks.map((m) => coordinate(m, "cx"))).toEqual([4, 636]);
    expect(marks.map((m) => coordinate(m, "cy"))).toEqual([115, 14]);
    expect(view.container.querySelectorAll("path")).toHaveLength(0);
  });

  it("retains a real zero as a visible observation at the baseline", () => {
    const view = render(<TrendChart series={[series([null, 0, null])]} labels={[]} />);
    const marks = view.container.querySelectorAll("circle");
    expect(marks).toHaveLength(1);
    expect(coordinate(marks[0], "cy")).toBe(216);
    expect(marks[0].getAttribute("aria-label")).toBe("ROAS: 0");
  });

  it("places right-axis singletons using the right scale and gutter", () => {
    const view = render(<TrendChart series={[
      series([10, null, null, null]),
      series([null, 50, null, 100], { label: "Clicks", axis: "right", color: "#654321" }),
    ]} labels={["Mon", "Tue", "Wed", "Thu"]} />);
    const marks = view.container.querySelectorAll('circle[fill="#654321"]');
    expect(marks).toHaveLength(2);
    expect(coordinate(marks[0], "cx")).toBeCloseTo(4 + 596 / 3);
    expect(coordinate(marks[0], "cy")).toBe(115);
    expect(coordinate(marks[1], "cx")).toBe(600);
    expect(coordinate(marks[1], "cy")).toBe(14);
  });

  it("preserves the area and connected stroke for a multi-point run", () => {
    const view = render(<TrendChart series={[series([1, 2])]} labels={["Mon", "Tue"]} />);
    expect(view.container.querySelectorAll("circle")).toHaveLength(0);
    expect(view.container.querySelectorAll("path")).toHaveLength(2);
    expect(view.container.querySelector('path[fill="none"]')?.getAttribute("d"))
      .toBe("M4.0,115.0 L636.0,14.0");
  });

  it("adds a mark beside a multi-point run without joining across its gap", () => {
    const view = render(<TrendChart series={[series([1, 2, null, 4])]} labels={[]} />);
    const marks = view.container.querySelectorAll("circle");
    expect(marks).toHaveLength(1);
    expect(coordinate(marks[0], "cx")).toBe(636);
    const strokes = view.container.querySelectorAll('path[fill="none"]');
    expect(strokes).toHaveLength(1);
    expect(strokes[0].getAttribute("d")).toBe("M4.0,175.6 L214.7,135.2");
  });

  it.each([
    { points: [] }, { points: [null] }, { points: [NaN] }, { points: [Infinity, -Infinity, null] },
  ])(
    "does not invent marks for an empty or unavailable population: $points", ({ points }) => {
      const view = render(<TrendChart series={[series(points)]} labels={[]} />);
      expect(view.container.querySelectorAll("circle, path")).toHaveLength(0);
      expect(view.container.querySelector("svg")?.outerHTML).not.toMatch(/NaN|Infinity/);
    },
  );

  it("updates marks when an observation disappears or joins a continuous run", () => {
    const view = render(<TrendChart series={[series([null, 2, null])]} labels={[]} />);
    expect(view.container.querySelectorAll("circle")).toHaveLength(1);
    view.rerender(<TrendChart series={[series([null, null, null])]} labels={[]} />);
    expect(view.container.querySelectorAll("circle, path")).toHaveLength(0);
    view.rerender(<TrendChart series={[series([1, 2, null])]} labels={[]} />);
    expect(view.container.querySelectorAll("circle")).toHaveLength(0);
    expect(view.container.querySelectorAll("path")).toHaveLength(2);
    view.unmount();
    const again = render(<TrendChart series={[series([2])]} labels={[]} />);
    expect(again.container.querySelectorAll("circle")).toHaveLength(1);
  });

  it("keeps each series' color and value when series order changes", () => {
    const a = series([1], { label: "A", color: "red" });
    const b = series([2], { label: "B", color: "blue" });
    const view = render(<TrendChart series={[a, b]} labels={[]} />);
    view.rerender(<TrendChart series={[b, a]} labels={[]} />);
    const marks = [...view.container.querySelectorAll("circle")];
    expect(marks.map((m) => [m.getAttribute("fill"), m.getAttribute("aria-label")]))
      .toEqual([["blue", "B: 2"], ["red", "A: 1"]]);
  });

  it("provides the exact series, date label and value on the point", () => {
    const view = render(<TrendChart series={[series([null, 0.25, null])]} labels={["Mon", "Tue", "Wed"]} />);
    const mark = view.container.querySelector("circle");
    expect(mark?.getAttribute("aria-label")).toBe("ROAS, Tue: 0.25");
    expect(mark?.querySelector("title")?.textContent).toBe("ROAS, Tue: 0.25");
  });

  it("does not mutate the supplied observations or labels", () => {
    const points = Object.freeze([null, 2, null]);
    const labels = ["Mon", "Tue", "Wed"];
    const before = [...labels];
    render(<TrendChart series={[series(points)]} labels={labels} />);
    expect(points).toEqual([null, 2, null]);
    expect(labels).toEqual(before);
  });
});
