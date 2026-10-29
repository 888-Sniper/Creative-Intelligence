/** Currency explanations kept independent of application or request state. */
export const sourceCurrencyMessages = {
  en: {
    preferred: "{metric} is shown in {source}. Your preferred currency is {preferred}; no conversion has been applied.",
    unknown: "The source currency for {metric} is unknown. This amount is unavailable.",
    mixed: "The source data for {metric} contains mixed currencies. A combined amount is unavailable.",
    benchmark: "Cost comparison unavailable: all displayed amounts must share one known source currency.",
    period: "Monetary changes require matching, known source currencies. Side amounts use their own currency; no conversion is applied.",
  },
  es: {
    preferred: "{metric} se muestra en {source}. Tu moneda preferida es {preferred}; no se ha aplicado ninguna conversión.",
    unknown: "Se desconoce la moneda de origen de {metric}. Este importe no está disponible.",
    mixed: "Los datos de origen de {metric} contienen varias monedas. No hay un importe combinado disponible.",
    benchmark: "Comparación de costes no disponible: todos los importes mostrados deben compartir una única moneda de origen conocida.",
    period: "Los cambios monetarios requieren monedas de origen conocidas e iguales. Los importes de cada período conservan su moneda; no se aplica ninguna conversión.",
  },
  pl: {
    preferred: "{metric}: kwota jest podana w {source}. Preferowana waluta to {preferred}; nie zastosowano przeliczenia.",
    unknown: "Waluta źródłowa dla {metric} jest nieznana. Ta kwota jest niedostępna.",
    mixed: "Dane źródłowe dla {metric} zawierają różne waluty. Łączna kwota jest niedostępna.",
    benchmark: "Porównanie kosztów jest niedostępne: wszystkie wyświetlane kwoty muszą być podane w jednej znanej walucie źródłowej.",
    period: "Zmiany kwot wymagają jednakowych, znanych walut źródłowych. Kwoty każdego okresu zachowują własną walutę; przeliczenie nie jest stosowane.",
  },
} as const;

export type SourceCurrencyKey = `sourceCurrency.${keyof typeof sourceCurrencyMessages.en}`;
export type SourceCurrencyTranslator = (key: SourceCurrencyKey, vars?: Record<string, string | number>) => string;
