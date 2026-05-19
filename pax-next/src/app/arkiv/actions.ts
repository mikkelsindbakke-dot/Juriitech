"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import {
  gemIArkiv,
  sletFraArkiv,
  type ArkivType,
} from "@/lib/queries/arkiv";
import { lavT } from "@/lib/i18n/t";
import type { Locale } from "@/lib/i18n/config";

// Henter den aktive brugers locale (effektiv_sprog). Bruges KUN til
// at vælge sprog på fejl-strenge der returneres til client.
async function _hentLocale(): Promise<Locale> {
  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) return "da";
    const db = await hentBrugerMedTenant(user.id);
    return db?.effektiv_sprog ?? "da";
  } catch {
    return "da";
  }
}

export async function gemIArkivAction(args: {
  titel: string;
  type: ArkivType;
  indhold: string;
  klageFilnavn?: string | null;
  spoergsmaal?: string | null;
  sagsakter?: string | null;
  ekstraInstrukser?: string | null;
}): Promise<{ ok: boolean; id?: number; fejl?: string }> {
  const locale = await _hentLocale();
  const t = lavT(locale);
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, fejl: t("arkiv.fejl_ikke_logget_ind") };

  const dbBruger = await hentBrugerMedTenant(user.id);
  if (!dbBruger) {
    return { ok: false, fejl: t("arkiv.fejl_ikke_linket_tenant") };
  }
  if (!args.titel?.trim() || !args.indhold?.trim()) {
    return { ok: false, fejl: t("arkiv.fejl_titel_indhold") };
  }

  try {
    const id = await gemIArkiv({
      ...args,
      tenantId: dbBruger.effektiv_tenant_id,
    });
    if (!id) {
      return { ok: false, fejl: t("arkiv.fejl_insert_uden_id") };
    }
    revalidatePath("/arkiv");
    return { ok: true, id };
  } catch (e) {
    return {
      ok: false,
      fejl: e instanceof Error ? e.message : t("arkiv.fejl_ukendt"),
    };
  }
}

export async function sletFraArkivAction(
  id: number,
): Promise<{ ok: boolean; fejl?: string }> {
  const locale = await _hentLocale();
  const t = lavT(locale);
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, fejl: t("arkiv.fejl_ikke_logget_ind") };

  const dbBruger = await hentBrugerMedTenant(user.id);
  if (!dbBruger) {
    return { ok: false, fejl: t("arkiv.fejl_ikke_linket_tenant") };
  }

  try {
    const ok = await sletFraArkiv(id, dbBruger.effektiv_tenant_id);
    if (!ok) {
      return { ok: false, fejl: t("arkiv.fejl_indgang_findes_ikke") };
    }
    revalidatePath("/arkiv");
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      fejl: e instanceof Error ? e.message : t("arkiv.fejl_ukendt"),
    };
  }
}
