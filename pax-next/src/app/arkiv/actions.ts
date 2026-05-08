"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import {
  gemIArkiv,
  sletFraArkiv,
  type ArkivType,
} from "@/lib/queries/arkiv";

export async function gemIArkivAction(args: {
  titel: string;
  type: ArkivType;
  indhold: string;
  klageFilnavn?: string | null;
  spoergsmaal?: string | null;
  sagsakter?: string | null;
  ekstraInstrukser?: string | null;
}): Promise<{ ok: boolean; id?: number; fejl?: string }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, fejl: "Ikke logget ind" };

  const dbBruger = await hentBrugerMedTenant(user.id);
  if (!dbBruger) {
    return { ok: false, fejl: "Ikke linket til tenant" };
  }
  if (!args.titel?.trim() || !args.indhold?.trim()) {
    return { ok: false, fejl: "Titel og indhold skal være udfyldt" };
  }

  try {
    const id = await gemIArkiv({
      ...args,
      tenantId: dbBruger.tenant_id,
    });
    if (!id) {
      return { ok: false, fejl: "Insert returnerede ingen id" };
    }
    revalidatePath("/arkiv");
    return { ok: true, id };
  } catch (e) {
    return {
      ok: false,
      fejl: e instanceof Error ? e.message : "Ukendt fejl",
    };
  }
}

export async function sletFraArkivAction(
  id: number,
): Promise<{ ok: boolean; fejl?: string }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, fejl: "Ikke logget ind" };

  const dbBruger = await hentBrugerMedTenant(user.id);
  if (!dbBruger) {
    return { ok: false, fejl: "Ikke linket til tenant" };
  }

  try {
    const ok = await sletFraArkiv(id, dbBruger.tenant_id);
    if (!ok) {
      return { ok: false, fejl: "Indgang findes ikke i din tenant" };
    }
    revalidatePath("/arkiv");
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      fejl: e instanceof Error ? e.message : "Ukendt fejl",
    };
  }
}
