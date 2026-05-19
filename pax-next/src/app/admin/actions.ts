"use server";

// Admin-handlinger: tenant-CRUD + bruger-management.
//
// SIKKERHED: Hver Action kalder requireAdmin() FØR den udfører noget.
// Layout'et gater også UI'en, men Actions må selv håndhæve adgang —
// en angriber kan kalde dem direkte med en gyldig session-cookie.
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import {
  hentBrugerMedTenant,
  hentUserById,
  hentUserByEmail,
  opretUser,
  sletUser,
  taelAdmins,
} from "@/lib/queries/users";
import {
  hentTenantBySlug,
  opretTenant,
  opdaterTenant,
  type TenantFelter,
  type TenantOpdater,
} from "@/lib/queries/tenants";
import { getAdminClient, genererTempPassword } from "@/lib/supabase/admin";
import { skrivGdprAudit } from "@/lib/queries/audit";
import { lavT } from "@/lib/i18n/t";
import type { Locale } from "@/lib/i18n/config";

type AktuelAdmin = {
  user_id: number;
  email: string;
  tenant_id: number;
  role: "admin" | "jurist";
  locale: Locale;
};

// Verificerer at den kaldende session tilhører en admin. Returnerer
// admin-info ved succes; throw'er ved fejl (Server Action propagerer
// til kalder med en pæn fejl).
async function requireAdmin(): Promise<AktuelAdmin> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  // Tidlig fejl uden locale — vi falder tilbage til dansk for de
  // helt tidlige fejl. Brugeren har alligevel ikke session-locale her.
  if (!user) throw new Error(lavT("da")("admin.actions.fejl_ikke_logget_ind"));
  const db = await hentBrugerMedTenant(user.id);
  if (!db || db.role !== "admin") {
    const locale = db?.effektiv_sprog ?? "da";
    throw new Error(lavT(locale)("admin.actions.fejl_kraever_admin"));
  }
  return {
    user_id: db.user_id,
    email: db.email,
    tenant_id: db.tenant_id,
    role: db.role,
    locale: db.effektiv_sprog ?? "da",
  };
}

type Resultat<T = undefined> =
  | { ok: true; data?: T }
  | { ok: false; fejl: string };

// ───── TENANTS ─────

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function valideerSlug(slug: string, t: ReturnType<typeof lavT>): string | null {
  if (!slug) return t("admin.actions.fejl_slug_tom");
  if (!SLUG_RE.test(slug)) return t("admin.actions.fejl_slug_format");
  if (slug.length > 32) return t("admin.actions.fejl_slug_lang");
  return null;
}

export async function opretTenantAction(
  felter: TenantFelter,
): Promise<Resultat<{ id: number }>> {
  let t = lavT("da");
  try {
    const aktuel = await requireAdmin();
    t = lavT(aktuel.locale);
    if (!felter.navn?.trim()) return { ok: false, fejl: t("admin.actions.fejl_navn_paakraevet") };
    const slug = felter.slug.trim();
    const slugFejl = valideerSlug(slug, t);
    if (slugFejl) return { ok: false, fejl: slugFejl };
    if (await hentTenantBySlug(slug)) {
      return { ok: false, fejl: t("admin.actions.fejl_slug_brugt", { slug }) };
    }
    const id = await opretTenant({ ...felter, slug });
    if (!id) return { ok: false, fejl: t("admin.actions.fejl_opret_tenant") };

    // GDPR audit (fail-safe)
    await skrivGdprAudit({
      handling: "admin_tenant_oprettet",
      tenantId: aktuel.tenant_id,
      userId: aktuel.user_id,
      userEmail: aktuel.email,
      sagId: slug,
      metadata: { ny_tenant_id: id, navn: felter.navn },
    });

    revalidatePath("/admin");
    return { ok: true, data: { id } };
  } catch (e) {
    return { ok: false, fejl: e instanceof Error ? e.message : t("admin.actions.fejl_ukendt") };
  }
}

export async function opdaterTenantAction(
  id: number,
  felter: TenantOpdater,
): Promise<Resultat> {
  let t = lavT("da");
  try {
    const aktuel = await requireAdmin();
    t = lavT(aktuel.locale);
    if (felter.navn !== undefined && !felter.navn.trim()) {
      return { ok: false, fejl: t("admin.actions.fejl_navn_paakraevet") };
    }
    const ok = await opdaterTenant(id, felter);
    if (!ok) return { ok: false, fejl: t("admin.actions.fejl_opdatering") };

    // GDPR audit (fail-safe)
    await skrivGdprAudit({
      handling: "admin_tenant_opdateret",
      tenantId: aktuel.tenant_id,
      userId: aktuel.user_id,
      userEmail: aktuel.email,
      sagId: String(id),
      metadata: { aendrede_felter: Object.keys(felter) },
    });

    revalidatePath("/admin");
    return { ok: true };
  } catch (e) {
    return { ok: false, fejl: e instanceof Error ? e.message : t("admin.actions.fejl_ukendt") };
  }
}

// ───── BRUGERE ─────

export async function inviterBrugerAction(args: {
  email: string;
  tenantId: number;
  role: "admin" | "jurist";
  fuldeNavn?: string;
}): Promise<Resultat<{ besked?: string }>> {
  let t = lavT("da");
  try {
    const aktuel = await requireAdmin();
    t = lavT(aktuel.locale);
    const email = args.email.trim().toLowerCase();
    if (!email) return { ok: false, fejl: t("admin.actions.fejl_email_paakraevet") };
    if (!args.tenantId) return { ok: false, fejl: t("admin.actions.fejl_tenant_paakraevet") };
    if (!["admin", "jurist"].includes(args.role)) {
      return { ok: false, fejl: t("admin.actions.fejl_ugyldig_rolle", { rolle: args.role }) };
    }

    if (await hentUserByEmail(email)) {
      return { ok: false, fejl: t("admin.actions.fejl_email_findes", { email }) };
    }

    // 1) Opret row i vores users-tabel UDEN supabase_user_id —
    //    linkes ved første login når brugeren klikker invite-link.
    const userId = await opretUser({
      email,
      tenantId: args.tenantId,
      role: args.role,
      fuldeNavn: args.fuldeNavn ?? "",
    });
    if (!userId) {
      return { ok: false, fejl: t("admin.actions.fejl_opret_db") };
    }

    // 2) Bed Supabase sende invite-email
    const admin = getAdminClient();
    try {
      await admin.auth.admin.inviteUserByEmail(email, {
        data: { full_name: args.fuldeNavn ?? "" },
      });

      // GDPR audit (fail-safe)
      await skrivGdprAudit({
        handling: "admin_user_inviteret",
        tenantId: aktuel.tenant_id,
        userId: aktuel.user_id,
        userEmail: aktuel.email,
        sagId: email,
        metadata: {
          ny_bruger_id: userId,
          ny_bruger_email: email,
          ny_bruger_role: args.role,
          ny_bruger_tenant_id: args.tenantId,
          metode: "invite_email",
        },
      });

      revalidatePath("/admin/brugere");
      return { ok: true };
    } catch (e) {
      const msg = (e instanceof Error ? e.message : String(e)).toLowerCase();
      if (msg.includes("already") && (msg.includes("registered") || msg.includes("exists"))) {
        // Brugeren har allerede en Supabase-konto. Send password-reset.
        try {
          await admin.auth.resetPasswordForEmail(email);

          // GDPR audit (fail-safe)
          await skrivGdprAudit({
            handling: "admin_user_inviteret",
            tenantId: aktuel.tenant_id,
            userId: aktuel.user_id,
            userEmail: aktuel.email,
            sagId: email,
            metadata: {
              ny_bruger_id: userId,
              ny_bruger_email: email,
              ny_bruger_role: args.role,
              metode: "password_reset_fallback",
            },
          });

          revalidatePath("/admin/brugere");
          return {
            ok: true,
            data: {
              besked: t("admin.actions.besked_havde_konto", { email }),
            },
          };
        } catch {
          return {
            ok: false,
            fejl: t("admin.actions.fejl_havde_konto_reset_fejlede", { email }),
          };
        }
      }
      return {
        ok: false,
        fejl: t("admin.actions.fejl_invite_email", { fejl: e instanceof Error ? e.message : String(e) }),
      };
    }
  } catch (e) {
    return { ok: false, fejl: e instanceof Error ? e.message : t("admin.actions.fejl_ukendt") };
  }
}

export async function opretBrugerMedTempPasswordAction(args: {
  email: string;
  tenantId: number;
  role: "admin" | "jurist";
  fuldeNavn?: string;
}): Promise<Resultat<{ tempPassword: string }>> {
  let t = lavT("da");
  try {
    const aktuel = await requireAdmin();
    t = lavT(aktuel.locale);
    const email = args.email.trim().toLowerCase();
    if (!email) return { ok: false, fejl: t("admin.actions.fejl_email_paakraevet") };
    if (!args.tenantId) return { ok: false, fejl: t("admin.actions.fejl_tenant_paakraevet") };
    if (!["admin", "jurist"].includes(args.role)) {
      return { ok: false, fejl: t("admin.actions.fejl_ugyldig_rolle", { rolle: args.role }) };
    }
    if (await hentUserByEmail(email)) {
      return { ok: false, fejl: t("admin.actions.fejl_email_findes", { email }) };
    }

    const tempPassword = genererTempPassword();
    const admin = getAdminClient();

    // 1) Opret i Supabase Auth med email_confirm=true (admin har vouchet)
    let supUserId: string;
    try {
      const { data, error } = await admin.auth.admin.createUser({
        email,
        password: tempPassword,
        email_confirm: true,
        user_metadata: { full_name: args.fuldeNavn ?? "" },
      });
      if (error) throw error;
      if (!data.user) throw new Error(t("admin.actions.fejl_ingen_user"));
      supUserId = data.user.id;
    } catch (e) {
      const msg = (e instanceof Error ? e.message : String(e)).toLowerCase();
      if (msg.includes("already")) {
        return {
          ok: false,
          fejl: t("admin.actions.fejl_supabase_konto_findes", { email }),
        };
      }
      return {
        ok: false,
        fejl: t("admin.actions.fejl_supabase_create", { fejl: e instanceof Error ? e.message : String(e) }),
      };
    }

    // 2) Link straks med supabase_user_id
    const userId = await opretUser({
      email,
      tenantId: args.tenantId,
      role: args.role,
      fuldeNavn: args.fuldeNavn ?? "",
      supabaseUserId: supUserId,
    });
    if (!userId) {
      return {
        ok: false,
        fejl: t("admin.actions.fejl_db_row"),
      };
    }

    // GDPR audit (fail-safe)
    await skrivGdprAudit({
      handling: "admin_user_oprettet",
      tenantId: aktuel.tenant_id,
      userId: aktuel.user_id,
      userEmail: aktuel.email,
      sagId: email,
      metadata: {
        ny_bruger_id: userId,
        ny_bruger_email: email,
        ny_bruger_role: args.role,
        ny_bruger_tenant_id: args.tenantId,
        metode: "temp_password",
      },
    });

    revalidatePath("/admin/brugere");
    return { ok: true, data: { tempPassword } };
  } catch (e) {
    return { ok: false, fejl: e instanceof Error ? e.message : t("admin.actions.fejl_ukendt") };
  }
}

export async function sletBrugerAction(userId: number): Promise<Resultat> {
  let t = lavT("da");
  try {
    const aktuel = await requireAdmin();
    t = lavT(aktuel.locale);

    const dbUser = await hentUserById(userId);
    if (!dbUser) return { ok: false, fejl: t("admin.actions.fejl_bruger_findes_ikke", { id: userId }) };

    // Spær: må ikke slette sig selv
    if (aktuel.user_id === dbUser.id) {
      return {
        ok: false,
        fejl: t("admin.actions.fejl_slet_selv"),
      };
    }

    // Spær: må ikke slette sidste admin
    if (dbUser.role === "admin" && (await taelAdmins()) <= 1) {
      return {
        ok: false,
        fejl: t("admin.actions.fejl_slet_sidste_admin"),
      };
    }

    // 1) Slet i Supabase Auth (hvis vi har deres UUID)
    if (dbUser.supabase_user_id) {
      const admin = getAdminClient();
      try {
        await admin.auth.admin.deleteUser(dbUser.supabase_user_id);
      } catch (e) {
        const msg = (e instanceof Error ? e.message : String(e)).toLowerCase();
        // Hvis Supabase-kontoen allerede er væk, fortsæt med DB-sletning
        const allerede_vaek =
          msg.includes("not found") || msg.includes("404") || msg.includes("no rows");
        if (!allerede_vaek) {
          return {
            ok: false,
            fejl: t("admin.actions.fejl_supabase_slet", { fejl: e instanceof Error ? e.message : String(e) }),
          };
        }
      }
    }

    // 2) Slet i vores users-tabel
    if (!(await sletUser(dbUser.id))) {
      return {
        ok: false,
        fejl: t("admin.actions.fejl_db_slet", { id: dbUser.id }),
      };
    }

    // GDPR audit (fail-safe)
    await skrivGdprAudit({
      handling: "admin_user_slettet",
      tenantId: aktuel.tenant_id,
      userId: aktuel.user_id,
      userEmail: aktuel.email,
      sagId: dbUser.email,
      metadata: {
        slettet_user_id: dbUser.id,
        slettet_user_email: dbUser.email,
        slettet_user_role: dbUser.role,
        slettet_user_tenant_id: dbUser.tenant_id,
      },
    });

    revalidatePath("/admin/brugere");
    return { ok: true };
  } catch (e) {
    return { ok: false, fejl: e instanceof Error ? e.message : t("admin.actions.fejl_ukendt") };
  }
}
