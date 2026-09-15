import { expect, test } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

/** Item 29: Search Reports shares one row and one height (36px) with
 *  the All Statuses / All Formats / All Time selects. Guards against
 *  the nested-input sizing regression that made the search 50px tall
 *  and wrapped All Time onto a second row. */
test.use({ viewport: { width: 1440, height: 1000 } });

test("reports filters share one row at equal height", async ({
  page,
  context,
}) => {
  const seeds = readSeeds();
  await context.addInitScript(() => {
    try {
      window.localStorage.setItem("ci-theme", "light");
    } catch {
      /* private mode: theme simply does not persist */
    }
  });
  await loginAs(context, page, seeds.admin, "/reports");
  const search = page.locator(".rep-search");
  await search.waitFor({ timeout: 10000 });
  const heights = await page.evaluate(() => {
    const r = (el: Element) => {
      const b = (el as HTMLElement).getBoundingClientRect();
      return { h: Math.round(b.height), y: Math.round(b.top) };
    };
    return Array.from(document.querySelectorAll(".rep-filters > *")).map(r);
  });
  expect(heights.length).toBe(4);
  for (const m of heights) {
    expect(m.h).toBe(36);
    expect(m.y).toBe(heights[0].y);
  }
});
