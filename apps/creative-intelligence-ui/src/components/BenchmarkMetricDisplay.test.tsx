import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BenchmarkMiniBars, BenchmarkMoneyCell } from "./BenchmarkMetricDisplay";
import { benchmarkChartData, type BenchmarkMetric, type BenchmarkRow } from "./benchmarkMetrics";
import { formatNativeMoney } from "./sourceCurrency";
import { sourceCurrencyMessages, type SourceCurrencyTranslator } from "../i18n/sourceCurrency";
import { benchmarkReportingMessages } from "../i18n/benchmarkReporting";

afterEach(cleanup);
function row(overrides: Partial<BenchmarkRow> = {}): BenchmarkRow {
  return { spend: 300, impressions: 1000, clicks: 100, conversions: 10, revenue: 600,
    cpm: 12, cpa: 30, cpc: 3, ctr: 0.1, roas: 2, n_ads: 2,
    currency: "GBP", currencies: ["GBP"], currency_known: true,
    mixed_currency: false, unknown_currency_contribution: false, ...overrides };
}
function translator(lang: keyof typeof sourceCurrencyMessages): SourceCurrencyTranslator {
  return (key, vars = {}) => {
    const name = key.slice("sourceCurrency.".length) as keyof typeof sourceCurrencyMessages.en;
    return sourceCurrencyMessages[lang][name].replace(/\{(\w+)\}/g, (_, field: string) => String(vars[field]));
  };
}
function moneyCell(value: BenchmarkRow, metric: "cpm" | "cpa" = "cpm") {
  return <table><tbody><tr><td><BenchmarkMoneyCell row={value} metric={metric} metricLabel={metric.toUpperCase()}
    locale="en" unavailable="Unavailable" t={translator("en")} /></td></tr></tbody></table>;
}
function chart(rows: BenchmarkRow[], metric: BenchmarkMetric = "cpa", lang: keyof typeof sourceCurrencyMessages = "en") {
  const data = benchmarkChartData(rows, metric);
  return <BenchmarkMiniBars groups={data.values.map((value, index) => ({ label: `Group ${index + 1}`, value }))}
    format={(value) => metric === "cpa" || metric === "cpm"
      ? formatNativeMoney(value, data.currency, lang, "Unavailable") : String(value)}
    unavailable="Unavailable" emptyLabel={data.currencyUnavailable
      ? sourceCurrencyMessages[lang].benchmark : benchmarkReportingMessages[lang].noValues} />;
}
function group(name: string) { return screen.getByRole("group", { name }); }
function bar(name: string) { return group(name).querySelector<HTMLElement>('[aria-hidden="true"]'); }

describe("benchmark money cells", () => {
  it("shows canonical native CPM even when raw totals imply a different ratio", () => {
    render(moneyCell(row({ cpm: 2.5 })));
    expect(screen.getByRole("cell").textContent).toMatch(/GBP\s+2\.50/);
    expect(screen.queryByRole("note")).toBeNull();
  });
  it("keeps mixed-currency CPM unavailable and explains why", () => {
    render(moneyCell(row({ cpm: null, currency: null, currencies: ["GBP", "EUR"],
      currency_known: false, mixed_currency: true })));
    expect(screen.getByRole("cell").textContent).toMatch(/^Unavailable/);
    expect(screen.getByRole("note").textContent).toContain("mixed currencies");
    expect(screen.getByRole("cell").textContent).not.toContain("300");
  });
  it("does not assign a currency to an older unknown-unit response", () => {
    render(moneyCell(row({ currency_known: undefined, currencies: undefined })));
    expect(screen.getByRole("cell").textContent).toMatch(/^Unavailable/);
    expect(screen.getByRole("note").textContent).toContain("unknown");
  });
  it("preserves missing canonical CPM and measured zero separately", () => {
    const view = render(moneyCell(row({ cpm: undefined })));
    expect(screen.getByRole("cell").textContent).toBe("Unavailable");
    view.rerender(moneyCell(row({ cpm: 0 })));
    expect(screen.getByRole("cell").textContent).toMatch(/GBP\s+0\.00/);
  });
  it("keeps missing CPA unavailable without inventing a currency problem", () => {
    render(moneyCell(row({ cpa: null }), "cpa"));
    expect(screen.getByRole("cell").textContent).toBe("Unavailable");
    expect(screen.queryByRole("note")).toBeNull();
  });
});

describe("nullable benchmark mini charts", () => {
  it("renders one measured CPA and one unavailable slot without a zero bar", () => {
    render(chart([row({ cpa: 12 }), row({ cpa: null })]));
    expect(group("Group 1").textContent).toMatch(/GBP\s+12\.00/);
    expect(group("Group 2").textContent).toBe("Unavailable");
    expect(bar("Group 1")).not.toBeNull();
    expect(bar("Group 2")).toBeNull();
  });
  it("does not shift group identity or colour when the first value is missing", () => {
    render(chart([row({ roas: null }), row({ roas: 2 }), row({ roas: 1 })], "roas"));
    expect(group("Group 1").textContent).toBe("Unavailable");
    expect(bar("Group 1")).toBeNull();
    expect(group("Group 2").textContent).toBe("2");
    expect(bar("Group 2")!.style.background).toBe("rgb(14, 159, 110)");
    expect(bar("Group 3")!.style.background).toBe("rgb(124, 107, 214)");
  });
  it("distinguishes measured zero from missing without a positive-height zero bar", () => {
    render(chart([row({ roas: 0 }), row({ roas: null })], "roas"));
    expect(group("Group 1").textContent).toBe("0");
    expect(bar("Group 1")!.style.height).toBe("0px");
    expect(group("Group 2").textContent).toBe("Unavailable");
    expect(bar("Group 2")).toBeNull();
  });
  it.each(["en", "es", "pl"] as const)("explains all-null values in %s", (lang) => {
    render(chart([row({ roas: null }), row({ roas: null })], "roas", lang));
    expect(screen.getByRole("note").textContent).toBe(benchmarkReportingMessages[lang].noValues);
    expect(bar("Group 1")).toBeNull();
    expect(bar("Group 2")).toBeNull();
  });
  it.each(["en", "es", "pl"] as const)("explains incomparable cost units in %s", (lang) => {
    render(chart([row(), row({ currency: "EUR", currencies: ["EUR"] })], "cpm", lang));
    expect(screen.getByRole("note").textContent).toBe(sourceCurrencyMessages[lang].benchmark);
    expect(group("Group 1").textContent).toBe("Unavailable");
    expect(group("Group 2").textContent).toBe("Unavailable");
  });
  it("retains usable dimensionless values across different currencies", () => {
    render(chart([row({ ctr: 0.1 }), row({ ctr: 0.2, currency: "EUR", currencies: ["EUR"] })], "ctr"));
    expect(group("Group 1").textContent).toBe("10");
    expect(group("Group 2").textContent).toBe("20");
    expect(screen.queryByRole("note")).toBeNull();
  });
  it("updates values and unavailable states across repeated results", () => {
    const view = render(chart([row({ cpa: 12 }), row({ cpa: null })]));
    view.rerender(chart([row({ cpa: null }), row({ cpa: 0 })]));
    expect(group("Group 1").textContent).toBe("Unavailable");
    expect(bar("Group 1")).toBeNull();
    expect(group("Group 2").textContent).toMatch(/GBP\s+0\.00/);
    expect(bar("Group 2")!.style.height).toBe("0px");
    view.rerender(chart([row({ cpa: null }), row({ cpa: null })]));
    expect(screen.getByRole("note")).toBeTruthy();
  });
  it("does not format null, undefined or nonfinite values as numbers", () => {
    const format = vi.fn(String);
    render(<BenchmarkMiniBars groups={[{ label: "Missing", value: null }, { label: "Absent", value: undefined },
      { label: "Invalid", value: NaN }]} format={format} unavailable="Unavailable" emptyLabel="No values" />);
    expect(format).not.toHaveBeenCalled();
    expect(within(group("Missing")).getByText("Unavailable")).toBeTruthy();
    expect(screen.getByRole("note").textContent).toBe("No values");
  });
});
