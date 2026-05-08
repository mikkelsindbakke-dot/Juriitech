"use client";

import { useTransition, useState } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { sletSagAction } from "@/app/sager/actions";

export function SletSagKnap({ id, titel }: { id: number; titel: string }) {
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
        toast.success(`Slettede "${titel}"`);
      } else {
        toast.error(`Kunne ikke slette: ${r.fejl}`);
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
      {pending ? "Sletter..." : bekræft ? "Bekræft slet" : "Slet"}
    </Button>
  );
}
