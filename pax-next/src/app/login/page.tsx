"use client";

import { useState, useTransition } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { login } from "./actions";

export default function LoginPage() {
  const [fejl, sætFejl] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function håndterSubmit(formData: FormData) {
    sætFejl(null);
    startTransition(async () => {
      const resultat = await login(formData);
      if (resultat?.error) {
        sætFejl(resultat.error);
      }
    });
  }

  return (
    <main className="flex flex-1 items-center justify-center bg-zinc-50 px-6 py-20">
      <Card className="w-full max-w-md border-zinc-200 shadow-sm">
        <CardHeader className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-3 w-3 rounded-full bg-amber-500" />
            <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Migrations-version · ikke i produktion
            </span>
          </div>
          <CardTitle className="text-2xl font-semibold tracking-tight">
            Log ind på juriitech PAX
          </CardTitle>
          <CardDescription className="text-sm text-zinc-600">
            Brug din eksisterende PAX-konto. Den nye Next.js-version peger
            mod samme Supabase-database, så credentials er identiske.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={håndterSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                placeholder="dig@firma.dk"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Adgangskode</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </div>
            {fejl && (
              <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 border border-red-200">
                {fejl}
              </div>
            )}
            <Button type="submit" className="w-full" disabled={pending}>
              {pending ? "Logger ind..." : "Log ind"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
