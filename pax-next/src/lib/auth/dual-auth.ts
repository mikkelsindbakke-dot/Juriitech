import "server-only";
import { createClient } from "@/lib/supabase/server";
import { createClient as createAdminClient } from "@supabase/supabase-js";
import { hentBrugerMedTenant, type BrugerMedTenant } from "@/lib/queries/users";

// Dual auth-helper: prøv først cookie-baseret session (browser-flow),
// fald så tilbage til Authorization: Bearer JWT (script + mobile clients).
// Denne fil bør IKKE eksponeres til client-side.

let _adminClient: ReturnType<typeof createAdminClient> | null = null;
function getAdminClient() {
  if (_adminClient) return _adminClient;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !serviceKey) {
    throw new Error(
      "Supabase admin-klient kan ikke initialiseres — env vars mangler.",
    );
  }
  _adminClient = createAdminClient(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return _adminClient;
}

/**
 * Returnerer DB-bruger eller null hvis ingen gyldig auth.
 * Prøver i rækkefølge:
 *   1. Cookie-baseret Supabase session (browser logged-in flow)
 *   2. Authorization: Bearer JWT (programmatisk adgang fra scripts)
 *
 * Hvis ingen virker → null. Caller skal returnere 401.
 */
export async function hentBrugerEllerNull(
  req: Request,
): Promise<BrugerMedTenant | null> {
  // ─── 1. Cookie-baseret session ───
  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (user) {
      const db = await hentBrugerMedTenant(user.id);
      if (db) return db;
    }
  } catch {
    // ignore — falder igennem til Bearer
  }

  // ─── 2. Authorization: Bearer JWT ───
  const authHeader = req.headers.get("authorization") ?? "";
  if (authHeader.toLowerCase().startsWith("bearer ")) {
    const jwt = authHeader.slice(7).trim();
    if (jwt) {
      try {
        const admin = getAdminClient();
        // Verificér JWT via supabase admin
        const { data, error } = await admin.auth.getUser(jwt);
        if (!error && data?.user) {
          const db = await hentBrugerMedTenant(data.user.id);
          if (db) return db;
        }
      } catch {
        // ignore
      }
    }
  }

  return null;
}
