# Visual Review (Approved References)

Side-by-side acceptance of the 14 approved product screens against the
reference images. Pixel assertions are deliberately absent from the
test suite (font rendering differs between developer machines and CI
runners, so a pixel gate would be flaky); this artifact-based review
is the acceptance gate.

## Where The Captures Come From

- Suite: `apps/creative-intelligence-ui/e2e/00-screens.spec.ts`
  (runs inside `pnpm test:e2e` against the seeded backend +
  production build).
- Every CI run uploads them as the `approved-screens` workflow
  artifact (`.github/workflows/ci.yml`), even when E2E fails.
- Local run: `pnpm --dir apps/creative-intelligence-ui test:e2e`,
  then open `apps/creative-intelligence-ui/test-results/screens/`.

## Viewport Matrix

| Capture pattern      | Viewport  | Routes                    |
| -------------------- | --------- | ------------------------- |
| `01-login.png`       | 1440x1000 | Login                     |
| `02-dashboard.png` … `14-settings.png` | 1440x1000 | All 14 screens |
| `02-dashboard-1280.png` … | 1280x800 | All 14 routes |
| `02-dashboard-1024.png` … | 1024x768 | All 14 routes |
| `02-dashboard-768.png` …  | 768x1024 | All 14 routes |
| `m-login.png` | 390x844 | Login |
| `m-dashboard.png` … `m-settings.png` (all 14 routes) | 390x844 | All 14 routes |
| `p-compare.png`, `p-insights.png`, `p-ask.png` | 1440x1000 | Populated Compare / Insights / Ask |

## Review Procedure

1. Download the `approved-screens` artifact for the commit under review.
2. Place each capture next to its same-numbered approved reference
   (`01` = login … `14` = settings).
3. Check spacing, sizing, fonts, card dimensions, chart proportions
   and copy; file a fix for any meaningful difference.
4. Sign off only when no meaningful differences remain.

## Deterministic Gate (Always Enforced)

For every route at every viewport the suite asserts the correct page
heading and zero horizontal overflow (`scrollWidth - innerWidth <= 1`).
A green run means composition holds everywhere; the artifact review
means it matches the references.
