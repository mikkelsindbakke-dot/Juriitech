"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { useT } from "@/lib/i18n/client";

type HealthRespons = {
  ok: boolean;
  service: string;
  version: string;
  moduler: Record<string, string>;
};

// Lille knap der pinger FastAPI's /api/health-endpoint og toaster
// resultatet — så vi kan verificere at Next.js (3000) og FastAPI
// (8000) faktisk taler sammen.
export function ApiHealthButton() {
  const t = useT();
  const [pending, startTransition] = useTransition();
  const [resultat, sætResultat] = useState<HealthRespons | null>(null);

  function ping() {
    startTransition(async () => {
      const url = process.env.NEXT_PUBLIC_API_URL;
      if (!url) {
        toast.error(t("api_health.mangler_url_fejl"));
        return;
      }
      try {
        const res = await fetch(`${url}/api/health`, { cache: "no-store" });
        if (!res.ok) {
          toast.error(t("api_health.api_status_fejl", { status: res.status }));
          return;
        }
        const data = (await res.json()) as HealthRespons;
        sætResultat(data);
        toast.success(
          data.ok
            ? t("api_health.ok_toast")
            : t("api_health.moduler_fejlede_toast"),
        );
      } catch (e) {
        const detalje = e instanceof Error ? e.message : t("api_health.ukendt_fejl");
        toast.error(t("api_health.kan_ikke_naa_api", { detalje }));
      }
    });
  }

  return (
    <div className="space-y-3">
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={ping}
        disabled={pending}
      >
        {pending ? t("api_health.pinger") : t("api_health.ping_knap")}
      </Button>

      {resultat && (
        <div className="rounded-md bg-zinc-100 p-3 text-xs space-y-1">
          <div>
            <span className="text-zinc-500">{t("api_health.service_label")}</span>{" "}
            {resultat.service} v{resultat.version}
          </div>
          <div className="text-zinc-500">{t("api_health.moduler_label")}</div>
          <ul className="ml-4 space-y-0.5">
            {Object.entries(resultat.moduler).map(([navn, status]) => (
              <li key={navn}>
                <span
                  className={
                    status === "ok" ? "text-green-700" : "text-red-700"
                  }
                >
                  {status === "ok" ? "✓" : "✗"}
                </span>{" "}
                <code className="text-zinc-700">{navn}</code>
                {status !== "ok" && (
                  <span className="text-red-700"> — {status}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
