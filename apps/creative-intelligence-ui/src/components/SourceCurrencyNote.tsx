import type { SourceCurrencyTranslator } from "../i18n/sourceCurrency";
import { knownSourceCurrency, type SourceCurrency } from "./sourceCurrency";

export function SourceCurrencyNote({ source, preferred, metric, t }: {
  source: SourceCurrency | null | undefined;
  preferred: string;
  metric: string;
  t: SourceCurrencyTranslator;
}) {
  const code = knownSourceCurrency(source);
  const wanted = preferred.trim().toUpperCase();
  if (code && (!wanted || code === wanted)) return null;
  const text = code ? t("sourceCurrency.preferred", { metric, source: code, preferred: wanted })
    : t(source?.mixed_currency ? "sourceCurrency.mixed" : "sourceCurrency.unknown", { metric });
  return <p className="panel-sub" role="note" style={{ margin: "10px 0 0" }}>{text}</p>;
}
