# Sample Pack Presenter Guide

One-time pack `foap-presentation-pack-v1`: ten fictional campaigns,
thirty creatives, all figures synthetic. Add it once via
Admin → Advanced → Demo Tools → Demo Data → **Add Demo Data Once**.
Deleted samples stay deleted; repeat clicks never duplicate.

## Suggested Date Range

The pack covers a fixed 180-day window ending the day before import
(shown on the Demo Data panel, e.g. 2026-03-17 → 2026-09-12 for a
September import). Set the Dashboard range to cover it.

## Validated Answers (Computed From Imported Rows)

- Strongest ROAS: **Find Your Focus** (~10.3x, Noven Audio).
- Clicks but converts weakly: **Slow Mornings Club** (highest CTR
  ~3.5%, ROAS only ~1.3x).
- Meta vs TikTok for Avenlo Skin: filter Client → Avenlo Skin, use
  the platform comparison; per-creative platform bias gives each
  platform a different winner.
- Most improved: **One Sip Ahead** (positive ramp); declining:
  **Move Beyond Monday** (negative ramp).
- High spend, not best: **The 6AM Commitment** (~$52k, ROAS ~2.0x).
- Underperformer: **Small Space, Big Possibilities** (ROAS ~1.3x).
- Converter to praise: **First Light Ritual** (ROAS ~7.2x on
  ~$37k spend).

## Ten-Step Journey

1. Open Dashboard (set the pack date range above).
2. Filter to one fictional client (e.g. Avenlo Skin).
3. Compare four campaigns with contrasting ROAS (Compare page has a
   saved “Four Contrasts” setup).
4. Open a creative; inspect hook, timing, retention curve.
5. Ask “Which campaign has the strongest ROAS and why?”
   (answer: Find Your Focus — see validated figures).
6. Review a suggested next test (Analyst findings).
7. Save/open an insight (Saved Insights).
8. Generate and download a real report (Reports page).
9. Edit one sample item (Admin → Demo Data → Rename).
10. Delete one sample campaign (impact preview → confirm) and show
    counts/charts update. It will not come back.

## Storage Note

Render Free has no persistent disk: a redeploy wipes the database
including the receipt. Re-run Add Demo Data Once on the fresh
database (nothing exists to resurrect). For deletions that survive
redeploys, attach a persistent disk or managed Postgres.
