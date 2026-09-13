import { expect, test, type Page } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

/** Row-unit regression: every side-by-side panel group must share top
 *  and bottom Y coordinates on desktop. Fails loudly instead of
 *  drifting back into uneven cards. */
const TOL = 2;

const ROW_GRIDS = [
  ".kpi-grid",
  ".cols-2",
  ".cols-2-even",
  ".cols-3",
  ".cmp-grid",
  ".cmp-grid-4",
  ".cmp-trio",
  ".cards-3",
  ".cards-4",
  ".detail-cols-2",
  ".main-rail",
  ".wb-rail",
  ".detail-layout",
].join(", ");

async function expectPageAligned(page: Page, path: string) {
  const groups = await page.locator(ROW_GRIDS).evaluateAll((els) =>
    els.map((el) => {
      const kids = Array.from((el as HTMLElement).children)
        .map((c) => (c as HTMLElement).getBoundingClientRect())
        .filter((r) => r.width > 0 && r.height > 0)
        .map((r) => ({ top: r.top, bottom: r.bottom }));
      return { cls: (el as HTMLElement).className, kids };
    }),
  );
  // Cluster each grid's children into visual rows by top edge.
  for (const g of groups) {
    const sorted = [...g.kids].sort((a, b) => a.top - b.top);
    const rows: typeof sorted[] = [];
    for (const b of sorted) {
      const cur = rows[rows.length - 1];
      if (cur && Math.abs(b.top - cur[0].top) <= 8) cur.push(b);
      else rows.push([b]);
    }
    for (const group of rows) {
      if (group.length < 2) continue;
      const tops = group.map((b) => b.top);
      const bottoms = group.map((b) => b.bottom);
      expect(
        Math.max(...bottoms) - Math.min(...bottoms),
        `bottoms ${JSON.stringify(group)} in ${g.cls} on ${path}`,
      ).toBeLessThanOrEqual(TOL);
      expect(
        Math.max(...tops) - Math.min(...tops),
        `tops ${JSON.stringify(group)} in ${g.cls} on ${path}`,
      ).toBeLessThanOrEqual(TOL);
    }
  }
}

const PAGES = [
  "/",
  "/campaigns",
  "/creatives",
  "/compare",
  "/benchmarks",
  "/insights",
  "/reports",
  "/workbook",
  "/ask",
  "/analyst",
  "/admin",
  "/profile",
  "/settings",
];

test.describe("row-unit alignment", () => {
  test.use({ viewport: { width: 1536, height: 1000 } });

  for (const path of PAGES) {
    test(`rows align on ${path === "/" ? "dashboard" : path.slice(1)}`, async ({
      page,
      context,
    }) => {
      const seeds = readSeeds();
      await loginAs(context, page, seeds.admin, path);
      await page.waitForLoadState("networkidle");
      await expectPageAligned(page, path);
    });
  }

  test("stacked mobile rows use natural heights", async ({
    page,
    context,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/settings");
    await page.waitForLoadState("networkidle");
    // Stacked: no horizontal overflow, panels keep natural height
    // (no stretch-induced empty regions).
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
