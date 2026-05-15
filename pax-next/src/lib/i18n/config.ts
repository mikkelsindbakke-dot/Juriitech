// Locale-konfiguration for juriitech PAX.
//
// Strategi: dansk er DEFAULT (alle danske tenants bruger den uændret).
// Norske + svenske + tyske strings ligger som OVERLAY der kun aktiveres
// når tenant.sprog matcher. Hvis en nøgle ikke findes på det valgte
// sprog, falder t() automatisk tilbage til dansk — så UI'et aldrig
// bliver tomt eller crasher pga. en manglende oversættelse.

export type Locale = "da" | "no" | "sv" | "de";

export const DEFAULT_LOCALE: Locale = "da";

export const SUPPORTED_LOCALES: Locale[] = ["da", "no", "sv", "de"];

// Validerer at en string er en supporteret locale. Bruges når vi læser
// fra tenant.sprog (DB-kolonne) — den KAN teknisk indeholde hvad som
// helst. Vi normaliserer altid til DEFAULT_LOCALE hvis værdien er
// ugyldig.
export function normaliserLocale(raw: string | null | undefined): Locale {
  if (!raw) return DEFAULT_LOCALE;
  const lower = raw.toLowerCase().slice(0, 2);
  if (SUPPORTED_LOCALES.includes(lower as Locale)) {
    return lower as Locale;
  }
  // Specielt: 'nb' (norsk bokmål) og 'nn' (nynorsk) mapper begge til 'no'
  if (lower === "nb" || lower === "nn") return "no";
  return DEFAULT_LOCALE;
}
