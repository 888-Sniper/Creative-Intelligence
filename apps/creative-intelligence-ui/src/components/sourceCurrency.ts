/** Source denomination only: neither preferences nor formatting perform FX. */
export interface SourceCurrency {
  currency?: string | null;
  currencies?: readonly string[] | null;
  currency_known?: boolean | null;
  mixed_currency?: boolean | null;
  unknown_currency_contribution?: boolean | null;
}

export interface PeriodCurrencyContext {
  current: SourceCurrency;
  previous: SourceCurrency;
  same_known_currency: boolean;
}

/** Missing or contradictory metadata cannot establish a known unit. */
export function knownSourceCurrency(source: SourceCurrency | null | undefined): string | null {
  if (!source || source.currency_known !== true || source.mixed_currency !== false
    || source.unknown_currency_contribution !== false) return null;
  const code = typeof source.currency === "string" ? source.currency.trim().toUpperCase() : "";
  if (!code || !Array.isArray(source.currencies) || source.currencies.length === 0) return null;
  return source.currencies.every((item) => typeof item === "string" && item.trim().toUpperCase() === code)
    ? code : null;
}

/** A consistent code can label an amount when the known-flag is absent.
 * An explicit false, a mix, or an unknown contribution cannot. */
export function displayCurrency(source: SourceCurrency | null | undefined): string | null {
  const known = knownSourceCurrency(source);
  if (known) return known;
  if (!source || source.mixed_currency || source.unknown_currency_contribution
    || source.currency_known === false) return null;
  const code = typeof source.currency === "string" ? source.currency.trim().toUpperCase() : "";
  if (!code) return null;
  const declared = source.currencies;
  if (declared == null) return code;
  return Array.isArray(declared) && declared.length > 0
    && declared.every((item) => typeof item === "string" && item.trim().toUpperCase() === code)
    ? code : null;
}

export function sharedSourceCurrency(
  groups: readonly (SourceCurrency & { n_ads?: number })[],
): string | null {
  const populated = groups.filter((group) => group.n_ads !== 0);
  if (!populated.length) return null;
  const first = knownSourceCurrency(populated[0]);
  return first && populated.every((group) => knownSourceCurrency(group) === first) ? first : null;
}

/** Require the explicit period contract as well as consistent source records. */
export function comparablePeriodCurrency(context: PeriodCurrencyContext | null | undefined): string | null {
  if (context?.same_known_currency !== true) return null;
  const current = knownSourceCurrency(context.current);
  return current && current === knownSourceCurrency(context.previous) ? current : null;
}

/** Preserve native amounts, with explicit codes even when Intl cannot format. */
export function formatNativeMoney(
  value: number | null | undefined, currency: string | null | undefined,
  locale: string, unavailable: string, options: { compact?: boolean; digits?: number } = {},
): string {
  const code = typeof currency === "string" ? currency.trim().toUpperCase() : "";
  if (value == null || !Number.isFinite(value) || !code) return unavailable;
  const compact = options.compact && Math.abs(value) >= 1_000;
  const digits = compact ? 1 : options.digits ?? 2;
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency", currency: code, currencyDisplay: "code",
      ...(compact ? { notation: "compact" } : {}),
      minimumFractionDigits: digits, maximumFractionDigits: digits,
    }).format(value);
  } catch {
    const amount = compact
      ? Math.abs(value) >= 1_000_000 ? `${(value / 1_000_000).toFixed(1)}M` : `${(value / 1_000).toFixed(1)}K`
      : value.toFixed(digits);
    return `${code} ${amount}`;
  }
}

export function sourceMoneyKpi(
  value: number | null | undefined, source: SourceCurrency | null | undefined,
  empty: boolean, locale: string, unavailable: string,
): string {
  const placeholder = empty && (value == null || !Number.isFinite(value));
  return formatNativeMoney(placeholder ? 0 : value, knownSourceCurrency(source), locale, unavailable,
    { compact: true, digits: placeholder ? 2 : 0 });
}
