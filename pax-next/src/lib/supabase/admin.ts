// Supabase admin-klient med SERVICE_ROLE-key.
// MÅ KUN BRUGES PÅ SERVER-SIDEN — service-key giver fuld DB-adgang
// uden RLS og må ALDRIG eksponeres i browseren.
//
// Bruges til admin-operationer:
//   - admin_invite_user_by_email (sender invite-email)
//   - admin.create_user (opretter med temp password, springer email-verifikation over)
//   - admin.delete_user (sletter Supabase Auth-konto)
import "server-only";
import { createClient } from "@supabase/supabase-js";

let _admin: ReturnType<typeof createClient> | null = null;

export function getAdminClient() {
  if (_admin) return _admin;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !serviceKey) {
    throw new Error(
      "SUPABASE_SERVICE_KEY mangler — admin-operationer er deaktiveret.",
    );
  }
  _admin = createClient(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return _admin;
}

// Genererer et sikkert 14-tegns password — bruger Web Crypto API.
// Garanterer mindst ét tegn fra hver klasse (store/små/tal/symbol)
// for at matche typiske password-policies.
export function genererTempPassword(length = 14): string {
  const stort = "ABCDEFGHJKLMNPQRSTUVWXYZ";
  const smaa = "abcdefghjkmnpqrstuvwxyz";
  const tal = "23456789";
  const symboler = "!@#$%&*";
  const alle = stort + smaa + tal + symboler;

  function vaelg(charset: string): string {
    const buf = new Uint32Array(1);
    crypto.getRandomValues(buf);
    return charset[buf[0] % charset.length];
  }

  const chars = [vaelg(stort), vaelg(smaa), vaelg(tal), vaelg(symboler)];
  for (let i = chars.length; i < length; i++) chars.push(vaelg(alle));
  // Bland rækkefølgen så de garanterede tegn ikke står først
  for (let i = chars.length - 1; i > 0; i--) {
    const buf = new Uint32Array(1);
    crypto.getRandomValues(buf);
    const j = buf[0] % (i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join("");
}
