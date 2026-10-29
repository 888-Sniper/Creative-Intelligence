import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { PERIOD_METRICS, PeriodComparisonTable, type PeriodResponse, type PeriodSide } from "./PeriodComparisonTable";
import { sourceCurrencyMessages, type SourceCurrencyTranslator } from "../i18n/sourceCurrency";

afterEach(cleanup);

function translator(lang: keyof typeof sourceCurrencyMessages): SourceCurrencyTranslator {
  return (key, vars = {}) => {
    const name = key.slice("sourceCurrency.".length) as keyof typeof sourceCurrencyMessages.en;
    return sourceCurrencyMessages[lang][name].replace(/\{(\w+)\}/g, (_, field: string) => String(vars[field]));
  };
}

function side(label: string, currency: string | null, value: number): PeriodSide {
  return { label, from: "2026-01-01", to: "2026-01-31", n_ads: 2,
    kpis: { ...Object.fromEntries(PERIOD_METRICS.map((metric) => [metric, value])),
      currency, currencies: currency ? [currency] : [], currency_known: currency !== null,
      mixed_currency: false, unknown_currency_contribution: currency === null } };
}

function response(a = side("First", "GBP", 100), b = side("Second", "GBP", 200)): PeriodResponse {
  return { a, b, delta: Object.fromEntries(PERIOD_METRICS.map((metric) => [metric, 100])) };
}

function table(data: PeriodResponse, lang: keyof typeof sourceCurrencyMessages = "en") {
  return <PeriodComparisonTable data={data} locale={lang} headings={{ metric: "Metric", delta: "B minus A", unavailable: "Unavailable" }}
    metricLabel={(metric) => metric} formatNonMoney={(metric, value) => value == null ? "Unavailable"
      : metric === "roas" ? `${value.toFixed(2)}x` : String(value)} t={translator(lang)} />;
}

function cells(metric: string) {
  const row = screen.getByRole("rowheader", { name: metric }).closest("tr")!;
  return within(row).getAllByRole("cell").map((cell) => cell.textContent);
}

describe("manual period currency presentation", () => {
  it("shows native side currencies and same-unit positive money deltas", () => {
    render(table(response()));
    expect(cells("spend")[0]).toMatch(/GBP\s+100\.00/);
    expect(cells("spend")[1]).toMatch(/GBP\s+200\.00/);
    expect(cells("spend")[2]).toMatch(/^\+GBP\s+100\.00/);
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("retains different native amounts and suppresses even an older numeric money delta", () => {
    render(table(response(side("First", "GBP", 100), side("Second", "EUR", 200))));
    expect(cells("spend")[0]).toMatch(/GBP\s+100\.00/);
    expect(cells("spend")[1]).toMatch(/EUR\s+200\.00/);
    for (const metric of ["spend", "cpm", "cpc", "cpa"]) expect(cells(metric)[2]).toBe("Unavailable");
    expect(cells("impressions")).toEqual(["100", "200", "+100"]);
    expect(cells("roas")).toEqual(["100.00x", "200.00x", "+100.00x"]);
  });

  it.each(["en", "es", "pl"] as const)("explains the currency requirement in %s", (lang) => {
    render(table(response(side("First", "GBP", 100), side("Second", "EUR", 200)), lang));
    expect(screen.getByRole("note").textContent).toBe(sourceCurrencyMessages[lang].period);
  });

  it("does not invent a unit for two unknown periods", () => {
    render(table(response(side("First", null, 100), side("Second", null, 200))));
    expect(cells("spend")).toEqual(["Unavailable", "Unavailable", "Unavailable"]);
    expect(screen.getAllByRole("note").map((note) => note.textContent)).toContain(
      "The source currency for First is unknown. This amount is unavailable.",
    );
  });

  it("hides mixed-unit totals but retains the known other side", () => {
    const data = response();
    data.a.kpis = { ...data.a.kpis, currency: null, currencies: ["GBP", "EUR"], currency_known: false, mixed_currency: true };
    render(table(data));
    expect(cells("spend")[0]).toBe("Unavailable");
    expect(cells("spend")[1]).toMatch(/GBP\s+200\.00/);
    expect(cells("spend")[2]).toBe("Unavailable");
    expect(screen.getAllByRole("note")[0].textContent).toContain("mixed currencies");
  });

  it("treats old responses without currency metadata as unknown", () => {
    const data = response();
    data.a.kpis = { spend: 100, impressions: 100 };
    render(table(data));
    expect(cells("spend")[0]).toBe("Unavailable");
    expect(cells("spend")[2]).toBe("Unavailable");
  });

  it("honours a server unavailability reason even if displayed metadata appears to match", () => {
    const data = { ...response(), delta_reasons: { cpa: "incomparable_currency" } };
    render(table(data));
    expect(cells("cpa")[2]).toBe("Unavailable");
    expect(cells("spend")[2]).toMatch(/^\+GBP/);
    expect(screen.getByRole("note").textContent).toBe(sourceCurrencyMessages.en.period);
  });

  it("preserves reported zero, negative changes and missing values distinctly", () => {
    const data = response();
    data.delta = { ...data.delta, spend: 0, cpa: -1.5, ctr: null };
    data.a.kpis.cpc = null;
    render(table(data));
    expect(cells("spend")[2]).toMatch(/^GBP\s+0\.00/);
    expect(cells("cpa")[2]).toMatch(/^−GBP\s+1\.50/);
    expect(cells("ctr")[2]).toBe("Unavailable");
    expect(cells("cpc")[0]).toBe("Unavailable");
  });

  it("keeps empty-side labels and counts without an invented monetary change", () => {
    const empty = { ...side("Empty", null, 0), n_ads: 0 };
    render(table(response(empty)));
    expect(cells("spend")[0]).toBe("Unavailable");
    expect(cells("spend")[2]).toBe("Unavailable");
    expect(screen.getByRole("columnheader", { name: /Empty.*n=0/ })).toBeTruthy();
    expect(screen.getAllByRole("note")).toHaveLength(1);
  });

  it("updates on repeated results without retaining the prior currency or reason", () => {
    const view = render(table(response()));
    expect(screen.queryByRole("note")).toBeNull();
    view.rerender(table(response(side("First", "GBP", 100), side("Second", "EUR", 200))));
    expect(cells("spend")[2]).toBe("Unavailable");
    expect(screen.getByRole("note")).toBeTruthy();
    view.rerender(table(response(side("Third", "EUR", 50), side("Fourth", "EUR", 150))));
    expect(cells("spend")[2]).toMatch(/^\+EUR/);
    expect(screen.queryByRole("note")).toBeNull();
    expect(screen.queryByText(/First \(/)).toBeNull();
  });

  it("keeps accessible table headings and the complete metric order", () => {
    render(table(response()));
    expect(screen.getAllByRole("columnheader")).toHaveLength(4);
    expect(screen.getAllByRole("rowheader").map((header) => header.textContent)).toEqual([...PERIOD_METRICS]);
    expect(screen.getByRole("columnheader", { name: "B minus A" })).toBeTruthy();
  });
});
