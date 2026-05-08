"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

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
  const [pending, startTransition] = useTransition();
  const [resultat, sætResultat] = useState<HealthRespons | null>(null);

  function ping() {
    startTransition(async () => {
      const url = process.env.NEXT_PUBLIC_API_URL;
      if (!url) {
        toast.error("NEXT_PUBLIC_API_URL ikke sat i .env.local");
        return;
      }
      try {
        const res = await fetch(`${url}/api/health`, { cache: "no-store" });
        if (!res.ok) {
          toast.error(`API svarede ${res.status}`);
          return;
        }
        const data = (await res.json()) as HealthRespons;
        sætResultat(data);
        toast.success(
          data.ok
            ? "FastAPI svarer OK — alle Python-moduler loadet"
            : "FastAPI kører, men nogle moduler fejlede import",
        );
      } catch (e) {
        toast.error(
          `Kan ikke nå API: ${e instanceof Error ? e.message : "ukendt fejl"}. ` +
            `Husk at starte uvicorn på port 8000.`,
        );
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
        {pending ? "Pinger..." : "Ping FastAPI"}
      </Button>

      {resultat && (
        <div className="rounded-md bg-zinc-100 p-3 text-xs space-y-1">
          <div>
            <span className="text-zinc-500">Service:</span> {resultat.service} v
            {resultat.version}
          </div>
          <div className="text-zinc-500">Python-moduler:</div>
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
