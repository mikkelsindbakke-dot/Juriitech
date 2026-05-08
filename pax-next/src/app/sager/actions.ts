"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import { gemSag, sletSag } from "@/lib/queries/gemte-sager";

// Server Action: gem en sag.
// Kontrollerer auth, slår tenant_id op via supabase_user_id, og
// kalder gemSag-querien som håndhæver tenant-ejerskab i SQL.
export async function gemSagAction(args: {
  titel: string;
  stateJson: string;
  sagId?: number;
}): Promise<{ ok: boolean; sagId?: number; fejl?: string }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, fejl: "Ikke logget ind" };

  const dbBruger = await hentBrugerMedTenant(user.id);
  if (!dbBruger) {
    return {
      ok: false,
      fejl: "Din konto er ikke linket til en tenant — kontakt admin",
    };
  }

  if (!args.titel?.trim()) {
    return { ok: false, fejl: "Titel mangler" };
  }
  if (!args.stateJson) {
    return { ok: false, fejl: "Tom state — intet at gemme" };
  }

  try {
    const sagId = await gemSag({
      titel: args.titel.trim(),
      stateJson: args.stateJson,
      userId: String(dbBruger.user_id),
      tenantId: dbBruger.tenant_id,
      sagId: args.sagId,
    });
    if (!sagId) {
      return {
        ok: false,
        fejl: "Sag tilhører anden tenant — afvist",
      };
    }
    revalidatePath("/sager");
    return { ok: true, sagId };
  } catch (e) {
    return {
      ok: false,
      fejl: e instanceof Error ? e.message : "Ukendt fejl",
    };
  }
}

export async function sletSagAction(
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
    const ok = await sletSag(id, dbBruger.tenant_id);
    if (!ok) {
      return { ok: false, fejl: "Sag findes ikke i din tenant" };
    }
    revalidatePath("/sager");
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      fejl: e instanceof Error ? e.message : "Ukendt fejl",
    };
  }
}
