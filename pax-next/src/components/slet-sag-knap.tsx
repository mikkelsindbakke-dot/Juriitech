"use client";

import { useTransition, useState } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { sletSagAction } from "@/app/sager/actions";
import { useIsAdmin, VENLIG_FEJL } from "@/lib/bruger-rolle";
import { useT } from "@/lib/i18n/client";

export function SletSagKnap({ id, titel }: { id: number; titel: string }) {
  const t = useT();
  const isAdmin = useIsAdmin();
  const [pending, startTransition] = useTransition();
  const [bekræft, sætBekræft] = useState(false);

  function håndter() {
    if (!bekræft) {
      sætBekræft(true);
      setTimeout(() => sætBekræft(false), 4000);
      return;
    }
    startTransition(async () => {
      const r = await sletSagAction(id);
      if (r.ok) {
        toast.success(t("slet_sag.slettede_toast", { titel }));
      } else {
        toast.error(
          isAdmin
            ? t("slet_sag.slet_admin_fejl", { fejl: r.fejl ?? "" })
            : VENLIG_FEJL,
        );
      }
      sætBekræft(false);
    });
  }

  return (
    <Button
      type="button"
      variant={bekræft ? "destructive" : "ghost"}
      size="sm"
      onClick={håndter}
      disabled={pending}
    >
      {pending
        ? t("knap.sletter")
        : bekræft
          ? t("knap.bekraeft_slet")
          : t("knap.slet")}
    </Button>
  );
}
