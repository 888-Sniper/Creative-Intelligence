import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { OverflowMenu } from "@/components/product";

function renderMenu(onSelect = vi.fn()) {
  render(
    <OverflowMenu
      label="Test actions"
      items={[
        { label: "Export", icon: "download", onSelect },
        { label: "Archive", onSelect: vi.fn() },
      ]}
    />,
  );
  return onSelect;
}

describe("OverflowMenu", () => {
  afterEach(() => {
    cleanup();
  });

  it("opens on toggle and selects an item", () => {
    const onSelect = renderMenu();
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Test actions" }));
    expect(screen.getByRole("menu")).toBeDefined();
    fireEvent.click(screen.getByRole("menuitem", { name: "Export" }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("dismisses on Escape and returns focus to the toggle", () => {
    renderMenu();
    const toggle = screen.getByRole("button", { name: "Test actions" });
    fireEvent.click(toggle);
    expect(screen.getByRole("menu")).toBeDefined();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(toggle);
  });

  it("moves between items with arrow keys", () => {
    renderMenu();
    fireEvent.click(screen.getByRole("button", { name: "Test actions" }));
    const items = screen.getAllByRole("menuitem");
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowUp" });
    expect(document.activeElement).toBe(items[0]);
  });
});
