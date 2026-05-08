// Hjælpe-funktion brugt af proxy.ts (Next.js 16's erstatning for
// middleware.ts). Kører ved HVER request og refresher Supabase-
// session-cookies hvis access-token er udløbet — så brugere ikke
// pludselig bliver logget ud midt i en flow.
//
// Hvis brugeren ikke er logget ind og prøver at tilgå en beskyttet
// route, redirect'es de til /login.
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  // VIGTIGT: getUser() — IKKE getSession() — så vi får verificeret
  // bruger fra Supabase Auth-server, ikke kun cookie-claim.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Liste over routes der ikke kræver login. Alt andet redirecter
  // til /login hvis bruger er null.
  const offentlige_paths = ["/login", "/auth"];
  const er_offentlig = offentlige_paths.some((p) =>
    request.nextUrl.pathname.startsWith(p),
  );

  if (!user && !er_offentlig) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}
