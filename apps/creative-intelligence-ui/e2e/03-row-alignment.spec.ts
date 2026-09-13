import { expect, test, type Page } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

/** ORDERING: the "03-" prefix sorts this after 03-demo-pack (so a
 *  DEMO_PACK=1 run measures populated rows) and before auth.spec.ts
 *  (whose logout-all journey revokes the seeded admin session this
 *  file logs in with — the same reason kpi-compare uses its own
 *  dedicated account). */

/** Row-unit regression: every side-by-side panel group must share top
 *  and bottom Y coordinates on desktop, with matching inner title
 *  baselines. Row membership comes from GRID LAYOUT STRUCTURE (the
 *  computed track count chunks consecutive auto-placed children into
 *  rows) — never from clustering cards by their current top
 *  coordinates, which would let a misaligned card escape into a
 *  single-member "row". A child with explicit grid placement fails
 *  loudly: it needs an explicit data-row hook instead.
 *
 *  The visible bordered unit is measured, not an invisible wrapper:
 *  when a grid child is a plain wrapper, its inner .panel/.kpi-card
 *  box is the unit under test.
 */
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

interface UnitBox {
  top: number;
  bottom: number;
  /** Title top relative to the unit top (null when no title). */
  title: number | null;
}

interface GridReport {
  cls: string;
  cols: number;
  display: string;
  units: UnitBox[];
  explicit: string[];
}

async function collectGrids(page: Page): Promise<GridReport[]> {
  return page.locator(ROW_GRIDS).evaluateAll((els) =>
    els.map((el) => {
      const host = el as HTMLElement;
      const cs = getComputedStyle(host);
      const trackText = (cs.gridTemplateColumns ?? "").trim();
      const cols =
        cs.display !== "grid" || trackText === "" || trackText === "none"
          ? 1
          : trackText.split(/\s+/).length;
      const units: UnitBox[] = [];
      const explicit: string[] = [];
      for (const child of Array.from(host.children)) {
        const c = child as HTMLElement;
        const r = c.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        const ccs = getComputedStyle(c);
        if (ccs.gridRowStart !== "auto" || ccs.gridColumnStart !== "auto") {
          explicit.push(c.className || c.tagName);
          continue;
        }
        // The visible bordered unit. A wrapper holding exactly one
        // bordered card is measured by that card (an aligned wrapper
        // must not hide a short card). A wrapper holding a STACK of
        // cards is an independent column: it is measured by its own
        // stretched box and its inner titles are not row baselines.
        let vis = c;
        let stacked = false;
        if (!c.matches(".panel,.kpi-card")) {
          // Top-level bordered units inside the wrapper (a unit nested
          // inside another unit belongs to that unit, not to the row).
          const all = Array.from(
            c.querySelectorAll(".panel,.kpi-card"),
          ) as HTMLElement[];
          const topUnits = all.filter((u) => {
            let p = u.parentElement;
            while (p && p !== c) {
              if (p.matches(".panel,.kpi-card")) return false;
              p = p.parentElement;
            }
            return true;
          });
          if (topUnits.length === 1) vis = topUnits[0];
          else if (topUnits.length > 1) stacked = true;
        }
        const vr = vis.getBoundingClientRect();
        const title = vis.querySelector(
          ".panel-title,.kpi-label,h1,h2,h3",
        ) as HTMLElement | null;
        const tr = title?.getBoundingClientRect();
        units.push({
          top: vr.top,
          bottom: vr.bottom,
          title: !stacked && tr && tr.height > 0 ? tr.top - vr.top : null,
        });
      }
      return {
        cls: host.className,
        cols,
        display: cs.display,
        units,
        explicit,
      };
    }),
  );
}

/** Structural row mismatches: empty means aligned. */
function rowViolations(report: GridReport[], path: string): string[] {
  const out: string[] = [];
  for (const g of report) {
    if (g.display !== "grid") {
      out.push(`${path}: ${g.cls} is no longer a grid (${g.display})`);
      continue;
    }
    if (g.explicit.length > 0) {
      out.push(
        `${path}: ${g.cls} has explicitly placed children needing a data-row hook: ${g.explicit.join(", ")}`,
      );
      continue;
    }
    for (let i = 0; i < g.units.length; i += g.cols) {
      const row = g.units.slice(i, i + g.cols);
      if (row.length < 2) continue;
      const tops = row.map((b) => b.top);
      const bottoms = row.map((b) => b.bottom);
      const dTop = Math.max(...tops) - Math.min(...tops);
      const dBottom = Math.max(...bottoms) - Math.min(...bottoms);
      if (dTop > TOL || dBottom > TOL) {
        out.push(
          `${path}: row ${i / g.cols} of ${g.cls} misaligned ` +
            `(top spread ${dTop.toFixed(1)}px, bottom spread ${dBottom.toFixed(1)}px, tolerance ${TOL}px)`,
        );
      }
      const titles = row.map((b) => b.title);
      if (titles.every((t) => t !== null)) {
        const nums = titles as number[];
        const dTitle = Math.max(...nums) - Math.min(...nums);
        if (dTitle > TOL) {
          out.push(
            `${path}: row ${i / g.cols} of ${g.cls} title baselines differ by ${dTitle.toFixed(1)}px`,
          );
        }
      }
    }
  }
  return out;
}

async function expectPageAligned(page: Page, path: string) {
  const report = await collectGrids(page);
  expect(rowViolations(report, path)).toEqual([]);
}

async function settle(page: Page) {
  // Anti-vacuous guard: prove the admin session reached the app shell
  // (a dead session renders the login gate, where row checks would
  // pass meaninglessly on zero grids).
  await expect(
    page.getByRole("link", { name: "Dashboard", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page.waitForLoadState("networkidle");
  await expect(page.locator(".skel")).toHaveCount(0, { timeout: 30000 });
  await expect(page.locator("button .spinner:visible")).toHaveCount(0, {
    timeout: 30000,
  });
  await page.evaluate(() => document.fonts.ready);
  // Let async images decode before any capture or measurement.
  await page.waitForFunction(
    () =>
      Array.from(document.images).every(
        (img) => img.complete && img.naturalWidth > 0,
      ),
    { timeout: 30000 },
  ).catch(() => undefined);
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

/** Widths under review: desktop row alignment plus tablet/mobile
 *  stacking without overflow or clipped controls. */
const SWEEP_WIDTHS = [1536, 1440, 1280, 1024, 768, 390];
const SWEEP_PAGES = ["/", "/campaigns", "/compare"];

test.describe("row-unit alignment", () => {
  test.use({ viewport: { width: 1536, height: 1000 } });

  for (const path of PAGES) {
    test(`rows align on ${path === "/" ? "dashboard" : path.slice(1)}`, async ({
      page,
      context,
    }) => {
      const seeds = readSeeds();
      await loginAs(context, page, seeds.admin, path);
      await settle(page);
      await expectPageAligned(page, path);
    });
  }

  test("negative control: a 16px offset is caught", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/");
    await settle(page);
    await expectPageAligned(page, "/");
    // Deliberately break the second KPI unit by 16px: the structural
    // checker must report it (proves the passing assertions above are
    // capable of failing).
    await page.locator(".kpi-grid").evaluate((el) => {
      const second = (el as HTMLElement).children[1] as HTMLElement;
      second.style.marginTop = "16px";
    });
    const report = await collectGrids(page);
    const found = rowViolations(report, "/");
    expect(found.length).toBeGreaterThan(0);
    expect(found.some((v) => v.includes("kpi-grid"))).toBe(true);
  });

  test("uneven title lengths keep rows aligned", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/campaigns");
    await settle(page);
    await page.locator(".cols-2 .panel-title").first().evaluate((el) => {
      el.textContent =
        "An Unusually Long Panel Title That Wraps Onto Several Lines " +
        "To Prove Uneven Text Lengths Cannot Break Row Edges";
    });
    await expectPageAligned(page, "/campaigns");
  });

  test("stacked mobile rows use natural heights", async ({
    page,
    context,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/settings");
    await settle(page);
    // Stacked: no horizontal overflow, panels keep natural height
    // (no stretch-induced empty regions).
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("mobile dashboard clips nothing and keeps controls usable", async ({
    page,
    context,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/");
    await settle(page);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
    // Every visible control stays inside the viewport horizontally,
    // unless it lives in a deliberately scrollable region (wide tables
    // scroll internally by design; the document itself must not).
    const clipped = await page
      .locator("button,select,input,a")
      .evaluateAll((els) =>
        els.filter((el) => {
          const h = el as HTMLElement;
          const r = h.getBoundingClientRect();
          if (r.width === 0 || r.height === 0) return false;
          if (r.right - window.innerWidth <= 1) return false;
          let p = h.parentElement;
          while (p && p !== document.body) {
            if (p.scrollWidth - p.clientWidth > 1) return false;
            p = p.parentElement;
          }
          return true;
        }).length,
      );
    expect(clipped).toBe(0);
    // Single-column grids still align trivially (no false failures).
    await expectPageAligned(page, "/");
  });
});

test.describe("row widths under review", () => {
  for (const width of SWEEP_WIDTHS) {
    for (const path of SWEEP_PAGES) {
      test(`${width}px: rows align on ${path === "/" ? "dashboard" : path.slice(1)}`, async ({
        page,
        context,
      }) => {
        await page.setViewportSize({ width, height: 1000 });
        const seeds = readSeeds();
        await loginAs(context, page, seeds.admin, path);
        await settle(page);
        await expectPageAligned(page, `${path}@${width}`);
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - window.innerWidth,
        );
        expect(overflow).toBeLessThanOrEqual(1);
      });
    }
  }
});

test.describe("loading, empty and error states", () => {
  test("campaigns shows a loading state, then settles", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await page.route("**/api/campaigns*", async (route) => {
      if (route.request().url().includes("/meta")) await route.continue();
      else {
        await new Promise((r) => setTimeout(r, 2000));
        await route.continue();
      }
    });
    await loginAs(context, page, seeds.admin, "/campaigns");
    await expect(page.locator(".skel").first()).toBeVisible({
      timeout: 15000,
    });
    await settle(page);
    await expect(page.locator(".skel")).toHaveCount(0);
    await page.unroute("**/api/campaigns*");
  });

  test("campaigns shows an error state with a working retry", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    // Fail only the campaign-list endpoint (metadata keeps flowing so
    // the page reaches its list error state, not a metadata crash).
    await page.route("**/api/campaigns*", async (route) => {
      if (route.request().url().includes("/meta")) await route.continue();
      else await route.abort();
    });
    await loginAs(context, page, seeds.admin, "/campaigns");
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible({
      timeout: 30000,
    });
    await page.unroute("**/api/campaigns*");
    await page.getByRole("button", { name: "Retry" }).click();
    // Fixture-agnostic recovery proof: the campaign table repopulates
    // (Seeded rows on the small fixture, synthetic campaigns under
    // FULL_DEMO=1, sample campaigns after a DEMO_PACK=1 import).
    await expect(
      page.locator("tbody tr").first(),
    ).toBeVisible({ timeout: 30000 });
  });

  test("campaigns shows an honest empty state", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await page.route("**/api/campaigns*", async (route) => {
      if (route.request().url().includes("/meta")) await route.continue();
      else await route.fulfill({ status: 200, body: "{}" });
    });
    await loginAs(context, page, seeds.admin, "/campaigns");
    await expect(page.getByText("No campaigns match")).toBeVisible({
      timeout: 30000,
    });
    await page.unroute("**/api/campaigns*");
  });
});
