"use client";

// Formular til at sætte ny adgangskode efter invite eller password-reset.
//
// Flow:
//   1. Brugeren skriver password + bekræft.
//   2. Submit kalder supabase.auth.verifyOtp({ token_hash, type })
//      som validerer tokenet og opretter en midlertidig session.
//   3. Derefter supabase.auth.updateUser({ password }) som sætter den
//      blivende adgangskode.
//   4. Linkning af Supabase-UUID til vores users-tabel sker automatisk
//      ved næste server-side request (hentBrugerMedTenant slår op via
//      supabase_user_id; hvis den ikke er sat, fallbacker den til email
//      og opdaterer rækken — analogt med Streamlit-PAX's
//      _link_supabase_to_db_user). Vi kalder router.push("/") og
//      Server Component'et ordner resten.
//
// Sikkerheds-overvejelser:
//   - verifyOtp accepterer kun tokenet ÉN gang. Hvis brugeren refresher
//     siden efter en fejl, skal de bede admin om en ny invitation.
//   - Vi rydder token_hash fra URL'en før redirect så det ikke
//     persisteres i browser-history.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";
import { useT } from "@/lib/i18n/client";

// De 30 mest almindelige svage adgangskoder — kopi af blacklisten i
// set_password.py så Next.js-flowet validerer ens med Streamlit-flowet.
const SVAGE_PASSWORDS = new Set([
  "12345678", "123456789", "1234567890", "qwerty12", "qwertyui",
  "qwerty123", "password", "password1", "password12", "password123",
  "passw0rd", "passw0rd1", "abc12345", "abcd1234", "letmein1",
  "welcome1", "welcome12", "welcome123", "admin123", "admin1234",
  "test1234", "test12345", "iloveyou1", "monkey123", "dragon123",
  "master123", "shadow123", "sunshine1", "princess1", "football1",
]);

// Returnerer en i18n-nøgle (eller null hvis OK). Selve oversættelsen
// sker i kalderen via useT() — så vi undgår at hardcode strings her.
function validerPasswordStyrke(pw: string): string | null {
  if (pw.length < 8) return "set_password.fejl_for_kort";
  if (SVAGE_PASSWORDS.has(pw.toLowerCase())) return "set_password.fejl_svag";
  const harBogstav = /[a-zA-ZæøåÆØÅ]/.test(pw);
  const harTal = /[0-9]/.test(pw);
  if (!harBogstav || !harTal) return "set_password.fejl_bogstav_og_tal";
  return null;
}

export function SetPasswordForm({
  tokenHash,
  type,
  erInvite,
}: {
  tokenHash: string;
  type: string;
  erInvite: boolean;
}) {
  const t = useT();
  const router = useRouter();
  const [pw1, sætPw1] = useState("");
  const [pw2, sætPw2] = useState("");
  const [fejl, sætFejl] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function håndterSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    sætFejl(null);

    if (!pw1 || !pw2) {
      sætFejl(t("set_password.fejl_begge_felter"));
      return;
    }
    if (pw1 !== pw2) {
      sætFejl(t("set_password.fejl_ikke_ens"));
      return;
    }
    const styrkeFejlNoegle = validerPasswordStyrke(pw1);
    if (styrkeFejlNoegle) {
      sætFejl(t(styrkeFejlNoegle));
      return;
    }

    startTransition(async () => {
      const supabase = createClient();

      // Step 1: verifyOtp — opretter midlertidig session via tokenet.
      // Supabase' TypeScript-typer accepterer type som EmailOtpType;
      // vi har allerede valideret i server component'et at type er en
      // af de tilladte værdier, så vi kan cast'e sikkert.
      const { error: verifyErr } = await supabase.auth.verifyOtp({
        token_hash: tokenHash,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        type: type as any,
      });
      if (verifyErr) {
        const msg = verifyErr.message.toLowerCase();
        const besked =
          msg.includes("expired") || msg.includes("invalid")
            ? t("set_password.fejl_link_udloebet")
            : t("set_password.fejl_aabne_link");
        sætFejl(besked);
        toast.error(besked);
        return;
      }

      // Step 2: updateUser — sætter selve passwordet.
      const { error: updErr } = await supabase.auth.updateUser({
        password: pw1,
      });
      if (updErr) {
        const besked = t("set_password.fejl_gem_password");
        sætFejl(besked);
        toast.error(besked);
        return;
      }

      toast.success(
        erInvite
          ? t("set_password.success_invite")
          : t("set_password.success_recovery"),
      );
      // Brugeren har nu en gyldig session i cookies. Server-component
      // på "/" henter dbBruger via hentBrugerMedTenant som linker
      // supabase_user_id ↔ users-row automatisk.
      // router.replace renser token_hash ud af history.
      router.replace("/");
      router.refresh();
    });
  }

  return (
    <form onSubmit={håndterSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="password">{t("set_password.ny_adgangskode_label")}</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          placeholder={t("set_password.ny_adgangskode_placeholder")}
          value={pw1}
          onChange={(e) => sætPw1(e.target.value)}
          disabled={pending}
          autoFocus
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="password-bekraeft">
          {t("set_password.bekraeft_adgangskode_label")}
        </Label>
        <Input
          id="password-bekraeft"
          name="password-bekraeft"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          placeholder={t("set_password.bekraeft_adgangskode_placeholder")}
          value={pw2}
          onChange={(e) => sætPw2(e.target.value)}
          disabled={pending}
        />
      </div>

      {fejl && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 border border-red-200">
          {fejl}
        </div>
      )}

      <Button
        type="submit"
        className="w-full"
        disabled={pending || !pw1 || !pw2}
      >
        {pending
          ? t("set_password.submit_gemmer")
          : erInvite
            ? t("set_password.submit_invite")
            : t("set_password.submit_recovery")}
      </Button>
    </form>
  );
}
