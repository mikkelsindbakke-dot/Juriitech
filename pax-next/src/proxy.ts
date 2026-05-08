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
    //   - _next/static (statiske assets)
    //   - _next/image (billede-optimering)
    //   - favicon.ico, robots.txt
    //   - filer med en udvidelse (.svg, .png osv.)
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
