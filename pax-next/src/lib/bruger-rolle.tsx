"use client";

// Bruger-rolle-context: eksponerer brugerens rolle (admin/jurist) til
// client-components, så fejlbeskeder kan filtreres.
//
// Almindelige brugere må ALDRIG se tekniske detaljer (kode, "API",
// "fetch", "error", status-kodes osv.) — de skal kun se en venlig
// generisk besked. Admin (Mikkel) skal stadig se de tekniske detaljer
// for at kunne diagnosticere fejl.
//
// Brug:
//   <BrugerRolleProvider isAdmin={...}>{children}</BrugerRolleProvider>
//   const formatFejl = useFejlBesked();
//   toast.error(formatFejl(e));   // admin ser tekniske detaljer, andre ser kun fallback

import { createContext, useContext } from "react";
import { ApiError } from "@/lib/api-client";

const AdminCtx = createContext(false);

export function BrugerRolleProvider({
  children,
  isAdmin,
}: {
  children: React.ReactNode;
  isAdmin: boolean;
}) {
  return <AdminCtx.Provider value={isAdmin}>{children}</AdminCtx.Provider>;
}

export function useIsAdmin(): boolean {
  return useContext(AdminCtx);
}

// Generisk venlig besked til alle ikke-admin brugere. Indeholder
// ingen tekniske ord (kode, API, fetch, error, status osv.) og altid
// med support-mail så brugeren ved hvor hjælpen kommer fra.
export const VENLIG_FEJL =
  "Noget gik galt. Prøv igen og kontakt juriitech@juriitech.com, hvis det stadig ikke virker.";

// Returnerer en formatter der konverterer en exception til en streng
// passende til toast/banner. Admin får teknisk detalje; alle andre
// får den venlige generiske besked.
export function useFejlBesked(): (e: unknown) => string {
  const isAdmin = useIsAdmin();
  return (e: unknown): string => {
    if (!isAdmin) return VENLIG_FEJL;
    if (e instanceof ApiError) {
      return e.detalje ? `${e.message}: ${e.detalje.slice(0, 200)}` : e.message;
    }
    return `Uventet fejl: ${e instanceof Error ? e.message : "ukendt"}`;
  };
}
