"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

// GDPR audit-helper: rapporter login/logout-event til FastAPI så vi
// får en row i gdpr_audit_log med user_id + tenant_id + IP. Fail-safe:
// fejler dette, går login/logout-flowet stadig igennem — audit er
// supplerende dokumentation, ikke en sikkerhedskontrol.
async function rapporterAuthEvent(
  variant: "login" | "logout",
  accessToken: string,
) {
  try {
    const path =
      variant === "login" ? "/api/auth/log-login" : "/api/auth/log-logout";
    // FastAPI'en kører co-located i samme container på port 8000 (intern)
    // — vi bruger relative URL'er via Next.js route /api/* proxy så vi
    // ikke skal hardcode host.
    // Server-side fetch fra Next.js → FastAPI. I prod kører de begge i
    // samme container (FastAPI på localhost:8000, Next på 8080), så vi
    // bruger localhost:8000. I dev hvor brugeren kører `next dev` mod
    // `uvicorn`-server lokalt: samme. Brug NEXT_PUBLIC_API_URL hvis sat
    // (matcher api-client.ts) ellers default localhost:8000.
    const apiBase =
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    await fetch(new URL(path, apiBase), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
      cache: "no-store",
    });
  } catch (e) {
    console.error(`audit-rapport (${variant}) fejlede:`, e);
  }
}

// Server Action: kaldes når login-formen submittes.
// Returnerer null ved succes (efter redirect), eller fejlbesked.
export async function login(formData: FormData) {
  const email = (formData.get("email") as string)?.trim();
  const password = formData.get("password") as string;

  if (!email || !password) {
    return { error: "Udfyld både email og adgangskode." };
  }

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });

  if (error) {
    // Supabase returnerer engelske fejlbeskeder — oversæt de mest
    // almindelige til dansk for vores brugere.
    const dansk =
      error.message === "Invalid login credentials"
        ? "Forkert email eller adgangskode."
        : error.message;
    return { error: dansk };
  }

  // GDPR audit: rapporter login_success — gør det FØR redirect så
  // session er aktiv. Fire-and-forget: vi venter ikke på svaret.
  const accessToken = data?.session?.access_token;
  if (accessToken) {
    await rapporterAuthEvent("login", accessToken);
  }

  // Succes: redirect til forsiden. redirect() kaster en speciel
  // exception som Next.js fanger — derfor ingen 'return' efter.
  redirect("/");
}

export async function logout() {
  const supabase = await createClient();
  // GDPR audit: rapporter logout FØR vi rydder sessionen — ellers er
  // JWT'en ugyldig når FastAPI prøver at validere den.
  try {
    const { data } = await supabase.auth.getSession();
    const accessToken = data?.session?.access_token;
    if (accessToken) {
      await rapporterAuthEvent("logout", accessToken);
    }
  } catch (e) {
    console.error("audit-rapport logout pre-fetch fejlede:", e);
  }
  await supabase.auth.signOut();
  redirect("/login");
}
