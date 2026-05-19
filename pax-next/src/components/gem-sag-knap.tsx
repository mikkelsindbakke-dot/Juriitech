"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { gemSagAction } from "@/app/sager/actions";
import { useIsAdmin, VENLIG_FEJL } from "@/lib/bruger-rolle";
import { useT } from "@/lib/i18n/client";

// Knap der gemmer den aktuelle analyse + svarbrev som en navngivet sag
// i gemte_sager-tabellen. Auth + tenant-isolation håndteres af
// Server Action — denne komponent sender bare titlen + JSON-state.
export function GemSagKnap({
  state,
  defaultTitel,
}: {
  state: object;
  defaultTitel?: string;
}) {
  const t = useT();
  const isAdmin = useIsAdmin();
  const [pending, startTransition] = useTransition();
  const [vises, sætVises] = useState(false);
  const [titel, sætTitel] = useState(defaultTitel ?? "");
  const [gemtId, sætGemtId] = useState<number | null>(null);

  function gem() {
    if (!titel.trim()) {
      toast.error(t("gem_sag.skriv_titel_fejl"));
      return;
    }
    startTransition(async () => {
      const r = await gemSagAction({
        titel,
        stateJson: JSON.stringify(state),
      });
      if (r.ok) {
        sætGemtId(r.sagId ?? null);
        toast.success(t("gem_sag.gemt_toast", { titel }));
      } else {
        toast.error(
          isAdmin ? t("gem_sag.gemt_admin_fejl", { fejl: r.fejl ?? "" }) : VENLIG_FEJL,
        );
      }
    });
  }

  if (gemtId !== null) {
    return (
      <div className="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-900">
        {t("gem_sag.gemt_kvittering_prefix", { id: gemtId })}
        <a
          href="/sager"
          className="underline underline-offset-2 hover:text-emerald-700"
        >
          {t("gem_sag.gemt_kvittering_link")}
        </a>
        {t("gem_sag.gemt_kvittering_suffix")}
      </div>
    );
  }

  if (!vises) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => sætVises(true)}
      >
        {t("gem_sag.knap_aabne")}
      </Button>
    );
  }

  return (
    <div className="rounded-md border border-zinc-200 bg-white p-3 space-y-2">
      <Label htmlFor="gem-titel" className="text-sm">
        {t("gem_sag.titel_label")}
      </Label>
      <Input
        id="gem-titel"
        value={titel}
        onChange={(e) => sætTitel(e.target.value)}
        placeholder={t("gem_sag.titel_placeholder")}
        disabled={pending}
        autoFocus
      />
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          onClick={gem}
          disabled={pending || !titel.trim()}
        >
          {pending ? t("gem_sag.gemmer") : t("gem_sag.gem")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => sætVises(false)}
          disabled={pending}
        >
          {t("gem_sag.annuller")}
        </Button>
      </div>
    </div>
  );
}
