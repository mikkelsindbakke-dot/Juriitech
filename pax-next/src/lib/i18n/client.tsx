"use client";

// Client-side i18n via React Context.
// Server components beregner locale (fra tenant.sprog) og sender det
// videre via <LocaleProvider locale="no"> i layout. Client-komponenter
// bruger useT() til at oversætte strings — og kalder altid t("nøgle")
// uden at tænke på locale.
//
// Hvis en client-komponent renderes UDENFOR en LocaleProvider (fx
// login-siden hvor brugeren endnu ikke har en tenant), bruges
// DEFAULT_LOCALE.

import { createContext, useContext, type ReactNode } from "react";
import type { Locale } from "./config";
import { DEFAULT_LOCALE } from "./config";
import { t as oversaet } from "./t";

const LocaleContext = createContext<Locale>(DEFAULT_LOCALE);

export function LocaleProvider({
  locale,
  children,
}: {
  locale: Locale;
  children: ReactNode;
}) {
  return (
    <LocaleContext.Provider value={locale}>
      {children}
    </LocaleContext.Provider>
  );
}

// Hook der returnerer en t()-funktion bundet til den aktive locale.
// Client-komponenter bruger: const t = useT(); <span>{t("login.titel")}</span>
export function useT() {
  const locale = useContext(LocaleContext);
  return (noegle: string, args?: Record<string, string | number>) =>
    oversaet(noegle, locale, args);
}

// Eksponér også den aktive locale hvis komponenten behøver den direkte
// (fx til <html lang>-attribut eller dato-formatering).
export function useLocale(): Locale {
  return useContext(LocaleContext);
}
