// Browser-side Supabase-klient.
// Bruges fra Client Components ('use client') der har brug for at
// kalde Supabase direkte fra browseren — fx login-forms, der lytter
// efter realtime-events, eller til at læse session efter login.
//
// Server Components SKAL bruge ./server.ts i stedet, så cookies
// håndteres korrekt.
import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
