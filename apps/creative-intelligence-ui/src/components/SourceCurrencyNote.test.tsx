import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SourceCurrencyNote } from "./SourceCurrencyNote";
import { sourceCurrencyMessages, type SourceCurrencyTranslator } from "../i18n/sourceCurrency";
import type { SourceCurrency } from "./sourceCurrency";

afterEach(cleanup);
const source: SourceCurrency = { currency: "GBP", currencies: ["GBP"], currency_known: true,
  mixed_currency: false, unknown_currency_contribution: false };

function translator(lang: keyof typeof sourceCurrencyMessages): SourceCurrencyTranslator {
  return (key, vars = {}) => {
    const name = key.slice("sourceCurrency.".length) as keyof typeof sourceCurrencyMessages.en;
    return sourceCurrencyMessages[lang][name].replace(/\{(\w+)\}/g, (_, field: string) => String(vars[field]));
  };
}

describe("source currency explanations", () => {
  it.each(["en", "es", "pl"] as const)("explains source GBP and preferred USD in %s", (lang) => {
    render(<SourceCurrencyNote source={source} preferred="USD" metric="Spend" t={translator(lang)} />);
    const note = screen.getByRole("note");
    expect(note.textContent).toContain("GBP");
    expect(note.textContent).toContain("USD");
    expect(note.textContent).toContain("Spend");
    expect(note.textContent).not.toContain("{");
  });
  it("identifies the actual source when the preference is another non-USD currency", () => {
    render(<SourceCurrencyNote source={source} preferred="EUR" metric="Total Spend" t={translator("en")} />);
    expect(screen.getByRole("note").textContent).toBe(
      "Total Spend is shown in GBP. Your preferred currency is EUR; no conversion has been applied.",
    );
  });
  it("does not show a conversion notice for a matching source and preference", () => {
    render(<SourceCurrencyNote source={source} preferred=" gbp " metric="Spend" t={translator("en")} />);
    expect(screen.queryByRole("note")).toBeNull();
  });
  it("reports an unknown source even when the preference is USD", () => {
    render(<SourceCurrencyNote source={undefined} preferred="USD" metric="Total Spend" t={translator("en")} />);
    expect(screen.getByRole("note").textContent).toBe(
      "The source currency for Total Spend is unknown. This amount is unavailable.",
    );
  });
  it("updates the explanation when a repeated render changes currency state", () => {
    const t = translator("en");
    const view = render(<SourceCurrencyNote source={undefined} preferred="USD" metric="Spend" t={t} />);
    expect(screen.getByRole("note").textContent).toContain("unknown");
    view.rerender(<SourceCurrencyNote source={{ ...source, mixed_currency: true }} preferred="USD" metric="Spend" t={t} />);
    expect(screen.getByRole("note").textContent).toContain("mixed currencies");
    view.rerender(<SourceCurrencyNote source={source} preferred="GBP" metric="Spend" t={t} />);
    expect(screen.queryByRole("note")).toBeNull();
    view.rerender(<SourceCurrencyNote source={source} preferred="EUR" metric="Spend" t={t} />);
    expect(screen.getByRole("note").textContent).toContain("shown in GBP");
  });
  it("keeps translation keys and substitution contracts aligned", () => {
    const vars = (value: string) => [...value.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
    for (const lang of ["es", "pl"] as const) {
      expect(Object.keys(sourceCurrencyMessages[lang])).toEqual(Object.keys(sourceCurrencyMessages.en));
      for (const key of Object.keys(sourceCurrencyMessages.en) as (keyof typeof sourceCurrencyMessages.en)[]) {
        expect(vars(sourceCurrencyMessages[lang][key])).toEqual(vars(sourceCurrencyMessages.en[key]));
      }
    }
  });
});
