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
    page.getByRole("heading", { name: "Analyze Video" }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/screens/vu-card.png" });

  // Open the panel and upload the real fixture clip.
  await page.getByRole("button", { name: /Upload Video/ }).click();
  await expect(
    page.getByRole("heading", { name: "Upload your video" }),
  ).toBeVisible();
  await page.getByLabel("Creative key").fill("video-upload-sample");
  await page.locator("#vu-file").setInputFiles(MP4);
  await page.getByRole("dialog").getByRole("button", { name: "Upload Video" }).click();
  await expect(page.getByText(/Video valid — 1280×720, 15s/)).toBeVisible();
  await expect(page.getByTestId("vu-video-preview")).toBeVisible();

  // Client/campaign: confirm the destination through the custom
  // names (seeded meta may be empty). Analysis requires this
  // confirmation; the campaign must match the fixture CSV grain.
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByRole("heading", { name: "Client and campaign" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /not in the catalogue/ }).click();
  await page.locator("#vu-client-custom").fill("E2E Client");
  await page.locator("#vu-campaign-custom").fill("Sample Launch");
  await page.getByRole("button", { name: "Confirm selection" }).click();
  await expect(page.getByText(/Selection confirmed/).first()).toBeVisible();

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
  // Stage D shows provider readiness before Analyze is submitted
  // (mock mode here: vision missing, so the server will refuse).
  await expect(page.getByText(/mock mode · vision missing/i)).toBeVisible();
  await expect(page.getByText(/What analysis sends/i)).toBeVisible();
  await page.screenshot({ path: "test-results/screens/vu-review.png" });

  // Confirm the match, then Analyze: no live provider in E2E, so the
  // endpoint must refuse honestly instead of queueing or mocking.
  await page.getByRole("button", { name: "Confirm match" }).click();
  await expect(page.getByText("Match confirmed.")).toBeVisible();
  const analyze = page.getByRole("button", { name: "Analyze" });
  await expect(analyze).toBeEnabled();
  await analyze.click();
  // The endpoint's exact refusal reason (mock-mode gating from
  // readiness()), not just the generic error wrapper: proves the
  // refusal is honest.
  await expect(page.getByText(/mock is active/i)).toBeVisible();

  // Recent uploads lists the draft with its real status (under the
  // file's real uploaded name).
  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: "Recent uploads" })).toBeVisible();
  await expect(page.getByText("Video Upload Sample 720p.mp4", { exact: true })).toBeVisible();
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
});

test("video remove drops the binding and never resurrects", async ({
  page, context,
}) => {
  const seeds = readSeeds();
  await loginAs(context, page, seeds.employee, "/");
  await page.getByRole("button", { name: /Upload Video/ }).click();
  await expect(
    page.getByRole("heading", { name: "Upload your video" }),
  ).toBeVisible();
  await page.getByLabel("Creative key").fill("video-upload-sample");
  await page.locator("#vu-file").setInputFiles(MP4);
  await page.getByRole("dialog").getByRole("button", { name: "Upload Video" }).click();
  await expect(page.getByText(/Video valid — 1280×720, 15s/)).toBeVisible();
  // Explicit backend removal: the preview and stored binding go.
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(page.getByTestId("vu-video-preview")).toBeHidden();
  // Reopen the pinned draft: the video stays gone (no resurrection
  // from the stored relationship), and re-upload works on the draft.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: "Recent uploads" })).toBeVisible();
  await page.getByRole("button", { name: "Resume" }).click();
  await expect(
    page.getByRole("heading", { name: "Upload your video" }),
  ).toBeVisible();
  await expect(page.getByTestId("vu-video-preview")).toBeHidden();
  await page.locator("#vu-file").setInputFiles(MP4);
  await page.getByRole("dialog").getByRole("button", { name: "Upload Video" }).click();
  await expect(page.getByText(/Video valid — 1280×720, 15s/)).toBeVisible();
  await expect(page.getByTestId("vu-video-preview")).toBeVisible();
});

test("video upload card stacks on a narrow viewport", async ({
  page, context,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const seeds = readSeeds();
  await loginAs(context, page, seeds.employee, "/");
  await expect(
    page.getByRole("heading", { name: "Analyze Video" }),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "test-results/screens/vu-mobile.png" });
});
