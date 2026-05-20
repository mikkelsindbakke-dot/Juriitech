"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { sletBrugerAction } from "@/app/admin/actions";
import type { Tenant } from "@/lib/queries/tenants";
import type { UserRow } from "@/lib/queries/users";
import { useRouter } from "next/navigation";
import { useT } from "@/lib/i18n/client";

type Data = { tenant: Tenant; users: UserRow[] }[];

export function BrugereAdmin({
  data,
  antalAdmins,
  aktuelUserId,
}: {
  data: Data;
  antalAdmins: number;
  aktuelUserId: number | null;
}) {
  const t = useT();
  if (data.length === 0) {
    return (
      <p className="text-sm text-zinc-500">
        {t("admin.brugere.ingen_tenants")}
      </p>
    );
  }
  return (
    <div className="space-y-4">
      {data.map(({ tenant, users }) => (
        <Card key={tenant.id}>
          <CardHeader>
            <CardTitle className="text-base font-semibold flex items-center justify-between">
              <span>{tenant.navn}</span>
              <span className="text-xs font-normal text-zinc-500">
                {users.length}{" "}
                {users.length === 1
                  ? t("admin.brugere.bruger_singular")
                  : t("admin.brugere.bruger_plural")}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {users.length === 0 ? (
              <p className="text-sm text-zinc-500">
                {t("admin.brugere.ingen_brugere_prefix")}{" "}
                <em>{t("admin.brugere.ingen_brugere_fane")}</em>.
              </p>
            ) : (
              <ul className="divide-y divide-zinc-100">
                {users.map((u) => (
                  <BrugerRække
                    key={u.id}
                    bruger={u}
                    erDigSelv={u.id === aktuelUserId}
                    erSidsteAdmin={u.role === "admin" && antalAdmins <= 1}
                  />
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function BrugerRække({
  bruger,
  erDigSelv,
  erSidsteAdmin,
}: {
  bruger: UserRow;
  erDigSelv: boolean;
  erSidsteAdmin: boolean;
}) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [bekræft, sætBekræft] = useState(false);

  const ikon = bruger.role === "admin" ? "🛡️" : "👤";
  const linkStatus = bruger.supabase_user_id
    ? t("admin.brugere.linket")
    : t("admin.brugere.ikke_linket");

  function håndter() {
    if (!bekræft) {
      sætBekræft(true);
      setTimeout(() => sætBekræft(false), 4000);
      return;
    }
    startTransition(async () => {
      const r = await sletBrugerAction(bruger.id);
      if (r.ok) {
        toast.success(t("admin.brugere.toast_slettet", { email: bruger.email }));
        router.refresh();
      } else {
        toast.error(r.fejl);
      }
      sætBekræft(false);
    });
  }

  return (
    <li className="flex items-center justify-between py-3">
      <div className="text-sm">
        <p>
          <span className="mr-2">{ikon}</span>
          <strong>{bruger.email}</strong>{" "}
          <span className="text-zinc-500">
            ({bruger.fulde_navn || "—"}) · {t("admin.brugere.role_label")}=
            <code className="text-xs">
              {bruger.role === "admin"
                ? t("admin.inviter.rolle_admin")
                : t("admin.inviter.rolle_jurist")}
            </code> · {linkStatus}
          </span>
        </p>
      </div>
      <div>
        {erDigSelv ? (
          <span className="text-xs text-zinc-400 italic">{t("admin.brugere.dig")}</span>
        ) : erSidsteAdmin ? (
          <span className="text-xs text-zinc-400 italic">
            {t("admin.brugere.sidste_admin")}
          </span>
        ) : (
          <Button
            type="button"
            variant={bekræft ? "destructive" : "ghost"}
            size="sm"
            onClick={håndter}
            disabled={pending}
          >
            {pending
              ? t("admin.brugere.knap_arbejder")
              : bekræft
                ? t("admin.brugere.knap_bekraeft_slet")
                : t("admin.brugere.knap_slet")}
          </Button>
        )}
      </div>
    </li>
  );
}
