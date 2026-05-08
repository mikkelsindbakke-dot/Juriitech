import { hentAlleTenants } from "@/lib/queries/tenants";
import { TenantsAdmin } from "@/components/admin/tenants-admin";

export default async function AdminTenantsPage() {
  const tenants = await hentAlleTenants();
  return <TenantsAdmin tenants={tenants} />;
}
