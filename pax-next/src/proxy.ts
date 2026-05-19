// Next.js 16 proxy — erstatter middleware.ts fra tidligere versioner.
// Kører i Node.js runtime (edge er IKKE understøttet i proxy).
//
// Funktion: refresh Supabase-session ved hver request, og redirect
// uautoriserede brugere til /login.
import { type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/proxy-helper";

export async function proxy(request: NextRequest) {
  return await updateSession(request);
}

export const config = {
  matcher: [
    // Match alle paths UNDTAGEN:
    //   - api/* — proxy må IKKE læse body'en på vores Route Handler
    //     fordi det udløser Next.js' default 10MB body-grænse selv
    //     med middlewareClientMaxBodySize sat. Route Handler i
    //     src/app/api/[...path]/route.ts har sin egen auth-bypass
    //     (FastAPI validerer Bearer-token), så proxy skal slet ikke
    //     røre /api/*. Fjernede 22MB+ ZIP-uploads til /api/foerstevurdering
    //     der ellers fejlede med 'fetch failed'.
    //   - _next/static (statiske assets)
    //   - _next/image (billede-optimering)
    //   - favicon.ico, robots.txt
    //   - filer med en udvidelse (.svg, .png osv.)
    "/((?!api/|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
