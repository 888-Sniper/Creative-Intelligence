import { expect, test } from "@playwright/test";
import path from "node:path";
import { readFileSync } from "node:fs";
import { loginAs, readSeeds } from "./helpers";

/** Guided video upload on an isolated E2E backend (seeded DB + tmp
 *  media dir): card placement, real mp4 upload + ffprobe validation,
 *  real CSV import, server-scoped match confirm, and the honest
 *  no-live-provider Analyze refusal. Synthetic fixtures only. */
const FIXTURES = path.resolve(process.cwd(), "..", "..", "fixtures");
const MP4 = path.join(FIXTURES, "Video Upload Sample 720p.mp4");
const CSV = readFileSync(
  path.join(FIXTURES, "Video Upload Sample Dataset.csv"), "utf-8");

test("dashboard video upload: real file, data, match, honest analyze", async ({
  page, context,
}) => {
  const seeds = readSeeds();
  await loginAs(context, page, seeds.employee, "/");

  // Card sits between the greeting and the filters.
  await expect(
    page.getByRole("heading", { name: "Analyze a video" }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/screens/vu-card.png" });

  // Open the panel and upload the real fixture clip.
  await page.getByRole("button", { name: /Upload video/ }).click();
  await expect(
    page.getByRole("heading", { name: "Upload your video" }),
  ).toBeVisible();
  await page.getByLabel("Creative key").fill("video-upload-sample");
  await page.locator("#vu-file").setInputFiles(MP4);
  await page.getByRole("dialog").getByRole("button", { name: "Upload video" }).click();
  await expect(page.getByText(/Video valid — 1280×720, 15s/)).toBeVisible();
  await expect(page.getByTestId("vu-video-preview")).toBeVisible();

  // Client/campaign: seeded meta may be empty; confirm only when the
  // seeded catalogue offers options.
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByRole("heading", { name: "Client and campaign" }),
  ).toBeVisible();

  // Dataset: paste the real fixture CSV and import through the
  // ingestion pipeline (dedup, provenance, quarantine).
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByRole("heading", { name: "Performance dataset" }),
  ).toBeVisible();
  await page.getByLabel("CSV data").fill(CSV);
  await page.getByRole("button", { name: "Import dataset" }).click();
  await expect(page.getByText("3 rows · 3 new · 0 updated").first()).toBeVisible();

  // Review: server-scoped candidate rows with checkboxes.
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByRole("heading", { name: "Review and analyze" }),
  ).toBeVisible();
  await expect(page.getByText("Sample Story V1").first()).toBeVisible();
  await page.screenshot({ path: "test-results/screens/vu-review.png" });

  // Confirm the match, then Analyze: no live provider in E2E, so the
  // endpoint must refuse honestly instead of queueing or mocking.
  await page.getByRole("button", { name: "Confirm match" }).click();
  await expect(page.getByText("Match confirmed.")).toBeVisible();
  const analyze = page.getByRole("button", { name: "Analyze" });
  await expect(analyze).toBeEnabled();
  await analyze.click();
  await expect(page.getByText(/Something went wrong/i)).toBeVisible();

  // Recent uploads lists the draft with its real status (under the
  // file's real uploaded name).
  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: "Recent uploads" })).toBeVisible();
  await expect(page.getByText("Video Upload Sample 720p.mp4")).toBeVisible();
  await expect(page.getByText("Draft")).toBeVisible();
});

test("video upload card stacks on a narrow viewport", async ({
  page, context,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const seeds = readSeeds();
  await loginAs(context, page, seeds.employee, "/");
  await expect(
    page.getByRole("heading", { name: "Analyze a video" }),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "test-results/screens/vu-mobile.png" });
});
