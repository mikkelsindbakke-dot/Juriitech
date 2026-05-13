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

  // SSO entry-point: juriitech.com-portalen sender brugeren hertil med
  // ?sso_token=<refresh_token>. Vi bytter token'et til en frisk session
  // (sætter cookies via wrappern ovenfor) og redirecter til /.
  //
  // VIGTIGT: Dette MÅ ligge i proxy/middleware fordi Server Components
  // ikke kan skrive auth-cookies — refreshSession() i en Server Component
  // fejler stille når den prøver at sætte de nye cookies, hvilket vil
  // sende brugeren videre til /dashboard uden cookies → middleware vil så
  // redirecte til /login.
  const ssoToken = request.nextUrl.searchParams.get("sso_token");
  if (ssoToken) {
    const { error } = await supabase.auth.refreshSession({
      refresh_token: ssoToken,
    });
    if (!error) {
      const url = request.nextUrl.clone();
      url.searchParams.delete("sso_token");
      url.pathname = "/";
      // Bevar Supabase-wrapperens Set-Cookie-headere på redirect-responsen
      // så browseren modtager dem sammen med Location-headeren.
      const redirectResp = NextResponse.redirect(url);
      const setCookies = supabaseResponse.headers.getSetCookie();
      setCookies.forEach((c) =>
        redirectResp.headers.append("Set-Cookie", c),
      );
      return redirectResp;
    }
    // Token allerede brugt eller udløbet — fald igennem. Hvis brugeren
    // allerede har en gyldig session via cookies, klares det af logikken
    // nedenfor; ellers redirecter den til /login.
  }

  // VIGTIGT: getUser() — IKKE getSession() — så vi får verificeret
  // bruger fra Supabase Auth-server, ikke kun cookie-claim.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Liste over routes der ikke kræver login. Alt andet redirecter
  // til /login hvis bruger er null.
  //
  // /api/* er undtaget fordi FastAPI-laget har sin egen auth-dependency
  // (Bearer JWT validation) — vi vil ikke sende API-konsumenter en
  // HTML-redirect-respons; de forventer JSON 401. Når browseren kalder
  // /api/* fra en logget-ind session, har den cookies med så denne
  // proxy stadig refresher sessionen (getUser()-kaldet ovenfor) inden
  // requesten proxies videre til uvicorn.
  const offentlige_paths = ["/login", "/auth", "/api"];
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
