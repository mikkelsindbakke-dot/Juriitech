"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import { gemSag, sletSag } from "@/lib/queries/gemte-sager";
import { lavT } from "@/lib/i18n/t";
import type { Locale } from "@/lib/i18n/config";

// Henter den aktive brugers locale (effektiv_sprog). Bruges KUN til
// at vælge sprog på fejl-strenge der returneres til client.
// Default = 'da' hvis bruger ikke kan slås op (samme som UI-fallback).
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

// Server Action: gem en sag.
// Kontrollerer auth, slår tenant_id op via supabase_user_id, og
// kalder gemSag-querien som håndhæver tenant-ejerskab i SQL.
export async function gemSagAction(args: {
  titel: string;
  stateJson: string;
  sagId?: number;
}): Promise<{ ok: boolean; sagId?: number; fejl?: string }> {
  const locale = await _hentLocale();
  const t = lavT(locale);
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, fejl: t("sag.fejl_ikke_logget_ind") };

  const dbBruger = await hentBrugerMedTenant(user.id);
  if (!dbBruger) {
    return {
      ok: false,
      fejl: t("sag.fejl_ikke_linket_tenant"),
    };
  }

  if (!args.titel?.trim()) {
    return { ok: false, fejl: t("sag.fejl_titel_mangler") };
  }
  if (!args.stateJson) {
    return { ok: false, fejl: t("sag.fejl_tom_state") };
  }

  try {
    const sagId = await gemSag({
      titel: args.titel.trim(),
      stateJson: args.stateJson,
      userId: String(dbBruger.user_id),
      tenantId: dbBruger.effektiv_tenant_id,
      sagId: args.sagId,
    });
    if (!sagId) {
      return {
        ok: false,
        fejl: t("sag.fejl_sag_anden_tenant"),
      };
    }
    revalidatePath("/sager");
    return { ok: true, sagId };
  } catch (e) {
    return {
      ok: false,
      fejl: e instanceof Error ? e.message : t("sag.fejl_ukendt"),
    };
  }
}

export async function sletSagAction(
  id: number,
): Promise<{ ok: boolean; fejl?: string }> {
  const locale = await _hentLocale();
  const t = lavT(locale);
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, fejl: t("sag.fejl_ikke_logget_ind") };

  const dbBruger = await hentBrugerMedTenant(user.id);
  if (!dbBruger) {
    return { ok: false, fejl: t("sag.fejl_ikke_linket_kort") };
  }

  try {
    const ok = await sletSag(id, dbBruger.effektiv_tenant_id);
    if (!ok) {
      return { ok: false, fejl: t("sag.fejl_sag_findes_ikke") };
    }
    revalidatePath("/sager");
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      fejl: e instanceof Error ? e.message : t("sag.fejl_ukendt"),
    };
  }
}
