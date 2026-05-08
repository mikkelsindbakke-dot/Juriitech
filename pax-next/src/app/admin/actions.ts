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

type AktuelAdmin = {
  user_id: number;
  email: string;
  tenant_id: number;
  role: "admin" | "jurist";
};

// Verificerer at den kaldende session tilhører en admin. Returnerer
// admin-info ved succes; throw'er ved fejl (Server Action propagerer
// til kalder med en pæn fejl).
async function requireAdmin(): Promise<AktuelAdmin> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("Ikke logget ind.");
  const db = await hentBrugerMedTenant(user.id);
  if (!db || db.role !== "admin") throw new Error("Kræver admin-rettigheder.");
  return {
    user_id: db.user_id,
    email: db.email,
    tenant_id: db.tenant_id,
    role: db.role,
  };
}

type Resultat<T = undefined> =
  | { ok: true; data?: T }
  | { ok: false; fejl: string };

// ───── TENANTS ─────

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function valideerSlug(slug: string): string | null {
  if (!slug) return "Slug må ikke være tom.";
  if (!SLUG_RE.test(slug))
    return "Slug må kun indeholde små bogstaver, tal og bindestreger (fx 'apollo-dk').";
  if (slug.length > 32) return "Slug må max være 32 tegn.";
  return null;
}

export async function opretTenantAction(
  felter: TenantFelter,
): Promise<Resultat<{ id: number }>> {
  try {
    await requireAdmin();
    if (!felter.navn?.trim()) return { ok: false, fejl: "Navn er påkrævet." };
    const slug = felter.slug.trim();
    const slugFejl = valideerSlug(slug);
    if (slugFejl) return { ok: false, fejl: slugFejl };
    if (await hentTenantBySlug(slug)) {
      return { ok: false, fejl: `Slug '${slug}' er allerede i brug.` };
    }
    const id = await opretTenant({ ...felter, slug });
    if (!id) return { ok: false, fejl: "Kunne ikke oprette tenant." };
    revalidatePath("/admin");
    return { ok: true, data: { id } };
  } catch (e) {
    return { ok: false, fejl: e instanceof Error ? e.message : "Ukendt fejl." };
  }
}

export async function opdaterTenantAction(
  id: number,
  felter: TenantOpdater,
): Promise<Resultat> {
  try {
    await requireAdmin();
    if (felter.navn !== undefined && !felter.navn.trim()) {
      return { ok: false, fejl: "Navn er påkrævet." };
    }
    const ok = await opdaterTenant(id, felter);
    if (!ok) return { ok: false, fejl: "Opdatering fejlede." };
    revalidatePath("/admin");
    return { ok: true };
  } catch (e) {
    return { ok: false, fejl: e instanceof Error ? e.message : "Ukendt fejl." };
  }
}

// ───── BRUGERE ─────

export async function inviterBrugerAction(args: {
  email: string;
  tenantId: number;
  role: "admin" | "jurist";
  fuldeNavn?: string;
}): Promise<Resultat<{ besked?: string }>> {
  try {
    await requireAdmin();
    const email = args.email.trim().toLowerCase();
    if (!email) return { ok: false, fejl: "Email er påkrævet." };
    if (!args.tenantId) return { ok: false, fejl: "Tenant er påkrævet." };
    if (!["admin", "jurist"].includes(args.role)) {
      return { ok: false, fejl: `Ugyldig rolle: ${args.role}` };
    }

    if (await hentUserByEmail(email)) {
      return { ok: false, fejl: `${email} er allerede oprettet.` };
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
      return { ok: false, fejl: "Kunne ikke oprette bruger i databasen." };
    }

    // 2) Bed Supabase sende invite-email
    const admin = getAdminClient();
    try {
      await admin.auth.admin.inviteUserByEmail(email, {
        data: { full_name: args.fuldeNavn ?? "" },
      });
      revalidatePath("/admin/brugere");
      return { ok: true };
    } catch (e) {
      const msg = (e instanceof Error ? e.message : String(e)).toLowerCase();
      if (msg.includes("already") && (msg.includes("registered") || msg.includes("exists"))) {
        // Brugeren har allerede en Supabase-konto. Send password-reset.
        try {
          await admin.auth.resetPasswordForEmail(email);
          revalidatePath("/admin/brugere");
          return {
            ok: true,
            data: {
              besked: `${email} havde allerede en Supabase-konto — vi har sendt et password-reset-link i stedet.`,
            },
          };
        } catch {
          return {
            ok: false,
            fejl: `${email} har allerede en Supabase-konto, og reset-link kunne ikke sendes. Slet manuelt i Supabase Dashboard og prøv igen.`,
          };
        }
      }
      return { ok: false, fejl: `Invite-email fejlede: ${e instanceof Error ? e.message : e}` };
    }
  } catch (e) {
    return { ok: false, fejl: e instanceof Error ? e.message : "Ukendt fejl." };
  }
}

export async function opretBrugerMedTempPasswordAction(args: {
  email: string;
  tenantId: number;
  role: "admin" | "jurist";
  fuldeNavn?: string;
}): Promise<Resultat<{ tempPassword: string }>> {
  try {
    await requireAdmin();
    const email = args.email.trim().toLowerCase();
    if (!email) return { ok: false, fejl: "Email er påkrævet." };
    if (!args.tenantId) return { ok: false, fejl: "Tenant er påkrævet." };
    if (!["admin", "jurist"].includes(args.role)) {
      return { ok: false, fejl: `Ugyldig rolle: ${args.role}` };
    }
    if (await hentUserByEmail(email)) {
      return { ok: false, fejl: `${email} er allerede oprettet.` };
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
      if (!data.user) throw new Error("Ingen user returneret fra Supabase.");
      supUserId = data.user.id;
    } catch (e) {
      const msg = (e instanceof Error ? e.message : String(e)).toLowerCase();
      if (msg.includes("already")) {
        return {
          ok: false,
          fejl: `${email} har allerede en Supabase Auth-konto. Slet i Supabase Dashboard først, eller brug 'Glemt adgangskode?'-flowet.`,
        };
      }
      return { ok: false, fejl: `Supabase create_user fejlede: ${e instanceof Error ? e.message : e}` };
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
        fejl: "Bruger oprettet i Supabase, men DB-row kunne ikke oprettes. Slet manuelt i Supabase Dashboard og prøv igen.",
      };
    }

    revalidatePath("/admin/brugere");
    return { ok: true, data: { tempPassword } };
  } catch (e) {
    return { ok: false, fejl: e instanceof Error ? e.message : "Ukendt fejl." };
  }
}

export async function sletBrugerAction(userId: number): Promise<Resultat> {
  try {
    const aktuel = await requireAdmin();

    const dbUser = await hentUserById(userId);
    if (!dbUser) return { ok: false, fejl: `Bruger med id=${userId} findes ikke.` };

    // Spær: må ikke slette sig selv
    if (aktuel.user_id === dbUser.id) {
      return {
        ok: false,
        fejl: "Du kan ikke slette din egen konto. Brug 'Log ud' i stedet.",
      };
    }

    // Spær: må ikke slette sidste admin
    if (dbUser.role === "admin" && (await taelAdmins()) <= 1) {
      return {
        ok: false,
        fejl: "Kan ikke slette den sidste administrator. Opret en anden admin først.",
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
            fejl: `Supabase-sletning fejlede: ${e instanceof Error ? e.message : e}. Bruger ikke slettet i vores DB.`,
          };
        }
      }
    }

    // 2) Slet i vores users-tabel
    if (!(await sletUser(dbUser.id))) {
      return {
        ok: false,
        fejl: `Slettet i Supabase, men DB-sletning fejlede. Slet manuelt: DELETE FROM users WHERE id=${dbUser.id}`,
      };
    }

    revalidatePath("/admin/brugere");
    return { ok: true };
  } catch (e) {
    return { ok: false, fejl: e instanceof Error ? e.message : "Ukendt fejl." };
  }
}
