import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { EmptyState } from "@/components/product";

describe("EmptyState lift", () => {
  afterEach(() => cleanup());

  it("adds no lift class by default", () => {
    const { container } = render(<EmptyState text="No hook benchmarks in scope." />);
    expect(container.querySelector(".empty-lift")).toBeNull();
  });

  it("lifts the text/icon group without touching panel layout", () => {
    const { container } = render(
      <EmptyState lift compact icon="compare" title="No Comparison Yet" text="Select two to four campaigns to compare." />,
    );
    const lifted = container.querySelector(".empty-structured.empty-lift");
    expect(lifted).not.toBeNull();
  });
});
