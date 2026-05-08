import { hentAlleTenants } from "@/lib/queries/tenants";
import { InviterAdmin } from "@/components/admin/inviter-admin";

export default async function AdminInviterPage() {
  const tenants = await hentAlleTenants();
  return <InviterAdmin tenants={tenants} />;
}
