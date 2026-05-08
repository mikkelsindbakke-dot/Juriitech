"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { gemSagAction } from "@/app/sager/actions";

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
  const [pending, startTransition] = useTransition();
  const [vises, sætVises] = useState(false);
  const [titel, sætTitel] = useState(defaultTitel ?? "");
  const [gemtId, sætGemtId] = useState<number | null>(null);

  function gem() {
    if (!titel.trim()) {
      toast.error("Skriv en titel.");
      return;
    }
    startTransition(async () => {
      const r = await gemSagAction({
        titel,
        stateJson: JSON.stringify(state),
      });
      if (r.ok) {
        sætGemtId(r.sagId ?? null);
        toast.success(`Gemt som "${titel}"`);
      } else {
        toast.error(`Kunne ikke gemme: ${r.fejl}`);
      }
    });
  }

  if (gemtId !== null) {
    return (
      <div className="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-900">
        ✓ Sagen er gemt (id #{gemtId}). Find den under{" "}
        <a
          href="/sager"
          className="underline underline-offset-2 hover:text-emerald-700"
        >
          Gemte sager
        </a>
        .
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
        Gem som sag
      </Button>
    );
  }

  return (
    <div className="rounded-md border border-zinc-200 bg-white p-3 space-y-2">
      <Label htmlFor="gem-titel" className="text-sm">
        Titel
      </Label>
      <Input
        id="gem-titel"
        value={titel}
        onChange={(e) => sætTitel(e.target.value)}
        placeholder="fx 'TUI · Gran Canaria pool-lukning'"
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
          {pending ? "Gemmer..." : "Gem"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => sætVises(false)}
          disabled={pending}
        >
          Annuller
        </Button>
      </div>
    </div>
  );
}
