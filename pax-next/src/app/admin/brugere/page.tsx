import { hentAlleTenants } from "@/lib/queries/tenants";
import { hentUsersForTenant, taelAdmins } from "@/lib/queries/users";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import { BrugereAdmin } from "@/components/admin/brugere-admin";

export default async function AdminBrugerePage() {
  const tenants = await hentAlleTenants();
  const usersPerTenant = await Promise.all(
    tenants.map(async (t) => ({
      tenant: t,
      users: await hentUsersForTenant(t.id),
    })),
  );
  const antalAdmins = await taelAdmins();

  // Den aktuelle admin (så vi kan disable slet-knap på vedkommende selv)
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const aktuelDb = user ? await hentBrugerMedTenant(user.id) : null;

  return (
    <BrugereAdmin
      data={usersPerTenant}
      antalAdmins={antalAdmins}
      aktuelUserId={aktuelDb?.user_id ?? null}
    />
  );
}
