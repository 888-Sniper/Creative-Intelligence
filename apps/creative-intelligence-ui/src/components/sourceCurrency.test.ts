import { describe, expect, it, vi } from "vitest";
import {
  comparablePeriodCurrency, formatNativeMoney, knownSourceCurrency, sharedSourceCurrency,
  sourceMoneyKpi, type SourceCurrency,
} from "./sourceCurrency";

function known(currency: string): SourceCurrency {
  return { currency, currencies: [currency], currency_known: true,
    mixed_currency: false, unknown_currency_contribution: false };
}

describe("source currency metadata", () => {
  it("normalizes an explicitly established unit", () => {
    expect(knownSourceCurrency({ ...known(" gbp "), currencies: ["GBP", "gbp"] })).toBe("GBP");
  });
  it.each([null, undefined, {}, { currency: "USD" },
    { ...known("GBP"), currency_known: false }, { ...known("GBP"), currency_known: null },
    { ...known("GBP"), mixed_currency: true }, { ...known("GBP"), mixed_currency: undefined },
    { ...known("GBP"), unknown_currency_contribution: true },
    { ...known("GBP"), unknown_currency_contribution: undefined },
    { ...known("GBP"), currencies: [] }, { ...known("GBP"), currencies: null },
    { ...known("GBP"), currencies: ["GBP", "EUR"] }, { ...known("GBP"), currency: " " },
  ])("does not infer a unit from incomplete or contradictory metadata: %j", (source) => {
    expect(knownSourceCurrency(source)).toBeNull();
  });
  it("requires one known currency across populated chart groups", () => {
    expect(sharedSourceCurrency([known("GBP"), known("gbp")])).toBe("GBP");
    expect(sharedSourceCurrency([known("GBP"), known("EUR")])).toBeNull();
    expect(sharedSourceCurrency([known("GBP"), {}])).toBeNull();
  });
  it("ignores explicitly empty groups without inventing a unit for an empty scope", () => {
    expect(sharedSourceCurrency([{ ...known("GBP"), n_ads: 3 }, { n_ads: 0 }])).toBe("GBP");
    expect(sharedSourceCurrency([])).toBeNull();
    expect(sharedSourceCurrency([{ ...known("GBP"), n_ads: 0 }])).toBeNull();
  });
  it("requires the explicit same-period flag and matching source metadata", () => {
    const current = known("GBP");
    expect(comparablePeriodCurrency({ current, previous: known("gbp"), same_known_currency: true })).toBe("GBP");
    expect(comparablePeriodCurrency({ current, previous: known("EUR"), same_known_currency: true })).toBeNull();
    expect(comparablePeriodCurrency({ current, previous: current, same_known_currency: false })).toBeNull();
    expect(comparablePeriodCurrency({ current, previous: {}, same_known_currency: true })).toBeNull();
    expect(comparablePeriodCurrency(undefined)).toBeNull();
  });
});

describe("native money display", () => {
  it.each(["GBP", "EUR", "USD"])("retains the amount and explicit %s denomination", (currency) => {
    const text = formatNativeMoney(25.5, currency, "en-US", "Unavailable");
    expect(text).toContain(currency);
    expect(text).toContain("25.50");
  });
  it.each(["en-US", "es-ES", "pl-PL"])("uses localized numbers for %s", (locale) => {
    expect(formatNativeMoney(1234.56, "GBP", locale, "Unavailable")).toBe(
      new Intl.NumberFormat(locale, { style: "currency", currency: "GBP", currencyDisplay: "code",
        minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(1234.56),
    );
  });
  it("preserves zero and negative amounts", () => {
    expect(formatNativeMoney(0, "EUR", "en", "Unavailable")).toContain("0.00");
    expect(formatNativeMoney(-25.5, "GBP", "en", "Unavailable")).toContain("25.50");
    expect(formatNativeMoney(-25.5, "GBP", "en", "Unavailable")).toContain("-");
  });
  it.each([null, undefined, NaN, Infinity, -Infinity])("keeps missing or nonfinite amounts unavailable: %s", (value) => {
    expect(formatNativeMoney(value, "GBP", "en", "No disponible")).toBe("No disponible");
  });
  it.each([null, undefined, "", " "])("never assumes dollars for an absent unit: %s", (currency) => {
    expect(formatNativeMoney(25, currency, "en", "Unavailable")).toBe("Unavailable");
  });
  it("keeps the requested unit in compact notation", () => {
    for (const value of [1000, 53_400, 1_500_000, -2500]) {
      const text = formatNativeMoney(value, "GBP", "en", "Unavailable", { compact: true });
      expect(text).toContain("GBP");
      expect(text).not.toContain("$");
    }
  });
  it("keeps the source label and amount if Intl rejects the locale", () => {
    expect(formatNativeMoney(25.5, "GBP", "invalid_locale", "Unavailable")).toBe("GBP 25.50");
    expect(formatNativeMoney(53_400, "EUR", "invalid_locale", "Unavailable", { compact: true })).toBe("EUR 53.4K");
  });
  it("keeps the source unit if Intl formatting itself is unavailable", () => {
    const mock = vi.spyOn(Intl, "NumberFormat").mockImplementation(() => { throw new Error("synthetic Intl failure"); });
    try {
      expect(formatNativeMoney(-1_500_000, "GBP", "en", "Unavailable", { compact: true })).toBe("GBP -1.5M");
      expect(formatNativeMoney(0, "EUR", "en", "Unavailable")).toBe("EUR 0.00");
    } finally {
      mock.mockRestore();
    }
  });
  it("does not mutate metadata when creating a spend card display", () => {
    const source = Object.freeze({ ...known("GBP"), currencies: Object.freeze(["GBP"]) });
    expect(sourceMoneyKpi(53_400, source, false, "en", "Unavailable")).toContain("GBP");
    expect(sourceMoneyKpi(53_400, source, false, "en", "Unavailable")).not.toContain("$");
    expect(source.currency).toBe("GBP");
  });
  it("distinguishes missing, measured zero and an empty placeholder without inventing currency", () => {
    expect(sourceMoneyKpi(null, known("GBP"), false, "en", "Unavailable")).toBe("Unavailable");
    expect(sourceMoneyKpi(0, known("GBP"), false, "en", "Unavailable")).toContain("GBP");
    expect(sourceMoneyKpi(null, known("GBP"), true, "en", "Unavailable")).toContain("0.00");
    expect(sourceMoneyKpi(null, undefined, true, "en", "Unavailable")).toBe("Unavailable");
    expect(sourceMoneyKpi(25, { ...known("GBP"), mixed_currency: true }, false, "en", "Unavailable")).toBe("Unavailable");
  });
});
