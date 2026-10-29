import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  benchmarkReportingMessages,
  type BenchmarkReportingKey, type BenchmarkReportingTranslator,
} from "../i18n/benchmarkReporting";
import { BenchmarkScopeNote } from "./BenchmarkScopeNote";
import { pooledBenchmark, type BenchmarkMetadata, type PooledBenchmarkMetric } from "./benchmarkPooling";

type Language = keyof typeof benchmarkReportingMessages;
type MessageName = keyof typeof benchmarkReportingMessages.en;

// Synthetic translation boundary using the actual new copy and the existing
// {name} interpolation contract; never imports the mixed locale dictionaries.
function translator(language: Language): BenchmarkReportingTranslator {
  return (key: BenchmarkReportingKey, vars) => {
    const name = key.replace("benchmarkReporting.", "") as MessageName;
    return benchmarkReportingMessages[language][name].replace(/\{(\w+)\}/g, (match, variable: string) =>
      vars?.[variable] === undefined ? match : String(vars[variable]));
  };
}

function group(metric: PooledBenchmarkMetric, numerator: number, denominator: number,
  extra: Record<string, number> = {}): BenchmarkMetadata {
  return {
    n_ads: 1, currency: "USD", currency_known: true, mixed_currency: false,
    metric_components: { [metric]: { numerator, denominator, reporting_rows: 1, total_rows: 1, ...extra } },
  };
}

afterEach(cleanup);

describe("scope baseline reporting note", () => {
  it("explains spend coverage for a partial ROAS population", () => {
    const result = pooledBenchmark([group("roas", 200, 100, { total_spend: 1000 })], "roas");
    render(<BenchmarkScopeNote active result={result} metric="roas" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toBe("ROAS uses 10% of spend with reported revenue.");
  });

  it("reports paired-input record coverage for common ratios", () => {
    const result = pooledBenchmark([group("ctr", 10, 100, { total_rows: 2 })], "ctr");
    render(<BenchmarkScopeNote active result={result} metric="ctr" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toBe("Inputs reported by 1 of 2 records (50%).");
  });

  it("does not describe measured zero revenue as missing", () => {
    const result = pooledBenchmark([group("roas", 0, 100, { total_spend: 100 })], "roas");
    render(<BenchmarkScopeNote active result={result} metric="roas" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toBe("ROAS uses 100% of spend with reported revenue.");
  });

  it("explains an unavailable relative change without calling the zero baseline missing", () => {
    const result = pooledBenchmark([group("roas", 0, 100, { total_spend: 100 })], "roas");
    render(<BenchmarkScopeNote active relativeComparison result={result} metric="roas" locale="en"
      t={translator("en")} label={benchmarkReportingMessages.en.roasBaseline} />);
    const text = screen.getByRole("status").textContent;
    expect(text).toContain("ROAS baseline");
    expect(text).toContain(benchmarkReportingMessages.en.zeroBaselineChange);
    expect(text).toContain("100% of spend");
    expect(text).not.toContain("Baseline unavailable");
    expect(result.value).toBe(0);
    expect(result.reason).toBeNull();
  });

  it("does not show the zero-baseline explanation for an available nonzero relative base", () => {
    const result = pooledBenchmark([group("roas", 200, 100, { total_spend: 100 })], "roas");
    render(<BenchmarkScopeNote active relativeComparison result={result} metric="roas" locale="en"
      t={translator("en")} label={benchmarkReportingMessages.en.roasBaseline} />);
    expect(screen.getByRole("status").textContent).not.toContain(benchmarkReportingMessages.en.zeroBaselineChange);
    expect(screen.getByRole("status").textContent).toContain("ROAS uses 100%");
  });

  it("removes the relative-only message when the same zero value is used as a direct baseline", () => {
    const result = pooledBenchmark([group("roas", 0, 100, { total_spend: 100 })], "roas");
    const view = render(<BenchmarkScopeNote active relativeComparison result={result} metric="roas"
      locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toContain(benchmarkReportingMessages.en.zeroBaselineChange);
    view.rerender(<BenchmarkScopeNote active result={result} metric="roas" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toBe("ROAS uses 100% of spend with reported revenue.");
  });

  it("keeps currency restrictions distinct from a measured zero relative base", () => {
    const result = pooledBenchmark([{ ...group("roas", 0, 100), mixed_currency: true }], "roas");
    render(<BenchmarkScopeNote active relativeComparison result={result} metric="roas"
      locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toBe(benchmarkReportingMessages.en.currency);
  });

  it("does not treat an empty-scope placeholder as a measured zero relative base", () => {
    const result = pooledBenchmark([], "roas");
    render(<BenchmarkScopeNote active relativeComparison result={result} metric="roas"
      locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toBe(benchmarkReportingMessages.en.empty);
  });

  it.each(["en", "es", "pl"] as const)("localizes the %s relative-change explanation and its context label", (language) => {
    const result = pooledBenchmark([group("roas", 0, 100, { total_spend: 100 })], "roas");
    render(<BenchmarkScopeNote active relativeComparison result={result} metric="roas" locale={language}
      t={translator(language)} label={benchmarkReportingMessages[language].roasBaseline} />);
    const text = screen.getByRole("status").textContent;
    expect(text).toContain(benchmarkReportingMessages[language].roasBaseline);
    expect(text).toContain(benchmarkReportingMessages[language].zeroBaselineChange);
  });

  it("explains why a mixed-currency baseline is absent", () => {
    const result = pooledBenchmark([{ ...group("roas", 200, 100), mixed_currency: true }], "roas");
    render(<BenchmarkScopeNote active result={result} metric="roas" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toBe(benchmarkReportingMessages.en.currency);
    expect(screen.getByRole("status").textContent).not.toContain("0%");
  });

  it("explains missing reporting metadata without fabricating coverage", () => {
    const result = pooledBenchmark([{ n_ads: 1 }], "ctr");
    render(<BenchmarkScopeNote active result={result} metric="ctr" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toBe(benchmarkReportingMessages.en.metadata);
  });

  it("distinguishes an empty scope from unreported inputs", () => {
    const empty = pooledBenchmark([], "ctr");
    const missing = pooledBenchmark([group("ctr", 0, 0, { reporting_rows: 0 })], "ctr");
    const view = render(<BenchmarkScopeNote active result={empty} metric="ctr" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toBe(benchmarkReportingMessages.en.empty);
    view.rerender(<BenchmarkScopeNote active result={missing} metric="ctr" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toContain(benchmarkReportingMessages.en.unreported);
    expect(screen.getByRole("status").textContent).toContain("0 of 1 records (0%)");
  });

  it.each([
    ["roas", "zeroSpend"], ["cpc", "zeroClicks"], ["cpa", "zeroConversions"],
    ["ctr", "zeroImpressions"], ["cpm", "zeroImpressions"],
  ] as const)("explains the measured zero denominator for %s", (metric, message) => {
    const result = pooledBenchmark([group(metric, 10, 0)], metric);
    render(<BenchmarkScopeNote active result={result} metric={metric} locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toContain(benchmarkReportingMessages.en[message]);
    expect(screen.getByRole("status").textContent).not.toContain(benchmarkReportingMessages.en.unreported);
  });

  it("reports unavailable coverage separately from an available baseline", () => {
    const result = pooledBenchmark([group("roas", 200, 100)], "roas");
    render(<BenchmarkScopeNote active result={result} metric="roas" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toBe(benchmarkReportingMessages.en.coverageUnavailable);
    expect(result.value).toBe(2);
  });

  it("does not round very small positive coverage down to an apparent zero", () => {
    const result = pooledBenchmark([group("roas", 2, 1, { total_spend: 100000 })], "roas");
    render(<BenchmarkScopeNote active result={result} metric="roas" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toContain("less than 0.1%");
  });

  it("does not round partial coverage up to an apparent complete population", () => {
    const result = pooledBenchmark([group("roas", 2, 99999, { total_spend: 100000 })], "roas");
    render(<BenchmarkScopeNote active result={result} metric="roas" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toContain("more than 99.9%");
    expect(screen.getByRole("status").textContent).not.toContain("100%");
  });

  it("removes the scope note for another baseline mode and restores the current result", () => {
    const partial = pooledBenchmark([group("ctr", 10, 100, { total_rows: 2 })], "ctr");
    const empty = pooledBenchmark([], "ctr");
    const view = render(<BenchmarkScopeNote active result={partial} metric="ctr" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toContain("50%");
    view.rerender(<BenchmarkScopeNote active={false} result={empty} metric="ctr" locale="en" t={translator("en")} />);
    expect(screen.queryByRole("status")).toBeNull();
    view.rerender(<BenchmarkScopeNote active result={empty} metric="ctr" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toBe(benchmarkReportingMessages.en.empty);
    expect(screen.getByRole("status").getAttribute("aria-live")).toBe("polite");
  });

  it("updates the explanation when the selected metric changes", () => {
    const a = pooledBenchmark([group("roas", 200, 100, { total_spend: 1000 })], "roas");
    const b = pooledBenchmark([group("cpc", 10, 0)], "cpc");
    const view = render(<BenchmarkScopeNote active result={a} metric="roas" locale="en" t={translator("en")} />);
    view.rerender(<BenchmarkScopeNote active result={b} metric="cpc" locale="en" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toContain("Reported clicks are zero");
    expect(screen.getByRole("status").textContent).not.toContain("ROAS uses");
  });

  it.each(["en", "es", "pl"] as const)("renders the actual %s currency explanation", (language) => {
    const result = pooledBenchmark([{ ...group("roas", 200, 100), currency_known: false }], "roas");
    render(<BenchmarkScopeNote active result={result} metric="roas" locale={language} t={translator(language)} />);
    expect(screen.getByRole("status").textContent).toBe(benchmarkReportingMessages[language].currency);
  });

  it("updates localized copy and number formatting without stale English text", () => {
    const result = pooledBenchmark([group("ctr", 10, 100, { total_rows: 3 })], "ctr");
    const view = render(<BenchmarkScopeNote active result={result} metric="ctr" locale="en" t={translator("en")} />);
    view.rerender(<BenchmarkScopeNote active result={result} metric="ctr" locale="es" t={translator("es")} />);
    expect(screen.getByRole("status").textContent).toContain("1 de 3 registros");
    expect(screen.getByRole("status").textContent).toContain("33,3");
    expect(screen.getByRole("status").textContent).not.toContain("Inputs reported");
  });

  it("keeps the note usable when an unsupported locale reaches the component", () => {
    const result = pooledBenchmark([group("ctr", 10, 100, { total_rows: 2 })], "ctr");
    render(<BenchmarkScopeNote active result={result} metric="ctr" locale="not_a_locale" t={translator("en")} />);
    expect(screen.getByRole("status").textContent).toContain("50%");
  });

  it("keeps the new namespace's message keys and interpolation fields in parity", () => {
    const keys = Object.keys(benchmarkReportingMessages.en).sort() as MessageName[];
    for (const language of ["es", "pl"] as const) {
      expect(Object.keys(benchmarkReportingMessages[language]).sort()).toEqual(keys);
      for (const key of keys) {
        const placeholders = (value: string) => [...value.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
        expect(placeholders(benchmarkReportingMessages[language][key]))
          .toEqual(placeholders(benchmarkReportingMessages.en[key]));
      }
    }
  });
});
