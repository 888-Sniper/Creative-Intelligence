import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { EmployeeAvatar, avatarInitials } from "@/components/product";

describe("avatarInitials", () => {
  it("uses name initials, then email, then a placeholder", () => {
    expect(avatarInitials("Ada Admin", "ada@foap.test")).toBe("AA");
    expect(avatarInitials("", "bo@foap.test")).toBe("B");
    expect(avatarInitials("", "")).toBe("?");
  });
});

describe("EmployeeAvatar", () => {
  afterEach(() => cleanup());

  it("renders the employee photo when a URL is available", () => {
    const { container } = render(
      <EmployeeAvatar url="https://pics.test/a.jpg" name="Ada Admin" email="ada@foap.test" />,
    );
    const img = container.querySelector("img.avatar");
    expect(img?.getAttribute("src")).toBe("https://pics.test/a.jpg");
  });

  it("renders initials when there is no photo", () => {
    const { container } = render(
      <EmployeeAvatar url="" name="Ada Admin" email="ada@foap.test" />,
    );
    expect(container.querySelector("img.avatar")).toBeNull();
    expect(screen.getByText("AA")).toBeDefined();
  });

  it("falls back to initials when the image genuinely fails", () => {
    const { container } = render(
      <EmployeeAvatar url="https://pics.test/broken.jpg" name="Bo B" email="bo@foap.test" />,
    );
    fireEvent.error(container.querySelector("img.avatar")!);
    expect(container.querySelector("img.avatar")).toBeNull();
    expect(screen.getByText("BB")).toBeDefined();
  });

  it("recovers the photo when the URL changes after a failure", () => {
    const { container, rerender } = render(
      <EmployeeAvatar url="https://pics.test/old.jpg" name="Cy C" email="cy@foap.test" />,
    );
    fireEvent.error(container.querySelector("img.avatar")!);
    expect(screen.getByText("CC")).toBeDefined();
    rerender(
      <EmployeeAvatar url="https://pics.test/new.jpg" name="Cy C" email="cy@foap.test" />,
    );
    expect(
      container.querySelector('img.avatar[src="https://pics.test/new.jpg"]'),
    ).not.toBeNull();
  });
});
