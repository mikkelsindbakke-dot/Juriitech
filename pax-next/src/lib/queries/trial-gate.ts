// Trial-gate: tjek om en bruger's HOME tenant er en udløbet prøveperiode.
//
// Bruges af proxy-helper.ts til at redirecte udløbede prøve-brugere til
// /proeve-udloebet. Holdt i sin egen fil så den kan kaldes både fra
// proxy (Node-runtime) og fra server components uden kreds-import.
//
// Designprincipper:
//  - Tjekker brugerens HOME tenant (users.tenant_id), IKKE effektiv-
//    tenant. Det betyder at en admin der bruger tenant-switcher til at
//    se en udløbet prøve-tenants data ikke selv blokeres.
//  - Konverterede prøver (trial_converted_at IS NOT NULL) tæller som
//    almindelige tenants → ingen blokering.
//  - Aktive prøver (trial_expires_at > NOW()) blokeres ikke.
//  - Fail-safe: hvis SQL fejler, returnerer vi false (giver adgang),
//    så en database-fejl ikke pludselig låser alle ude.
import "server-only";
import { query } from "@/lib/db";

export type ProeveStatus = {
  is_trial: boolean;
  expired: boolean;
  expires_at: string | null;
};

/**
 * Slår direkte op via Supabase Auth UUID for at finde brugerens
 * HOME tenant's trial-status. Én indexed SQL-query (~1ms).
 *
 * Returnerer expired=true KUN hvis tenanten er en aktiv prøve der er
 * udløbet OG ikke konverteret. Alle andre tilfælde (almindelig tenant,
 * aktiv prøve, konverteret prøve) returnerer expired=false.
 */
export async function hentProeveStatusForBruger(
  supabaseUserId: string,
): Promise<ProeveStatus> {
  try {
    const rows = await query<{
      is_trial: boolean;
      trial_expires_at: string | null;
      trial_converted_at: string | null;
    }>(
      `
      SELECT t.is_trial, t.trial_expires_at, t.trial_converted_at
        FROM users u
        JOIN tenants t ON t.id = u.tenant_id
       WHERE u.supabase_user_id = $1
       LIMIT 1
      `,
      [supabaseUserId],
    );
    const r = rows[0];
    if (!r) return { is_trial: false, expired: false, expires_at: null };
    const expired =
      !!r.is_trial &&
      !r.trial_converted_at &&
      !!r.trial_expires_at &&
      new Date(r.trial_expires_at).getTime() < Date.now();
    return {
      is_trial: !!r.is_trial,
      expired,
      expires_at: r.trial_expires_at,
    };
  } catch (e) {
    console.warn("trial-gate: status-lookup fejlede:", e);
    return { is_trial: false, expired: false, expires_at: null };
  }
}

/**
 * Convenience-wrapper der KUN returnerer boolean — den eneste
 * information proxy-laget faktisk har brug for.
 */
export async function erProeveUdloebetForBruger(
  supabaseUserId: string,
): Promise<boolean> {
  const status = await hentProeveStatusForBruger(supabaseUserId);
  return status.expired;
}
