// Server-side Supabase-klient.
// Bruges fra Server Components, Server Actions og Route Handlers.
//
// VIGTIGT (Next.js 16): cookies() er nu async og skal afventes.
// Det er en breaking change fra Next.js 15.
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // setAll kaldt fra Server Component — ignoreres når
            // proxy.ts allerede refresher session ved hver request.
          }
        },
      },
    },
  );
}
