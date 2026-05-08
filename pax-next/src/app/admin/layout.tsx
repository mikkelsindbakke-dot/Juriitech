import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";

// Admin-layout: gater alle /admin/*-ruter på role='admin'.
// Adgangskontrol sker SERVER-SIDE — ingen ikke-admin kan få JSX'en
// dumpet, heller ikke ved at gætte URL'en. Sidemenu med tabs vises
// til alle admin-sider.
export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const dbBruger = await hentBrugerMedTenant(user.id);
  if (!dbBruger || dbBruger.role !== "admin") {
    redirect("/");
  }

  return (
    <main className="flex-1 bg-zinc-50">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
              <span className="text-amber-600">🛡️</span>
              Administration
            </h1>
            <p className="text-sm text-zinc-500">
              Logget ind som <strong>{dbBruger.email}</strong> (administrator)
            </p>
          </div>
          <Link
            href="/"
            className="text-sm text-zinc-500 hover:text-zinc-900 underline-offset-4 hover:underline"
          >
            ← Tilbage til forsiden
          </Link>
        </div>

        <nav className="flex gap-1 border-b border-zinc-200 mb-6">
          <AdminTabLink href="/admin">Tenants</AdminTabLink>
          <AdminTabLink href="/admin/brugere">Brugere</AdminTabLink>
          <AdminTabLink href="/admin/inviter">Inviter ny bruger</AdminTabLink>
        </nav>

        {children}
      </div>
    </main>
  );
}

function AdminTabLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="px-4 py-2 text-sm font-medium text-zinc-600 hover:text-zinc-900 border-b-2 border-transparent hover:border-zinc-300 -mb-px"
    >
      {children}
    </Link>
  );
}
