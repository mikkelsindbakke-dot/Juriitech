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
import { PaxLogo } from "@/components/pax-logo";
import { useT } from "@/lib/i18n/client";
import { login } from "./actions";

export function LoginFormClient() {
  const t = useT();
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
      <div className="w-full max-w-md space-y-6">
        <div className="flex justify-center">
          <PaxLogo size="lg" />
        </div>
        <Card className="border-zinc-200 shadow-sm">
          <CardHeader className="space-y-2">
            <CardTitle className="text-2xl font-semibold tracking-tight">
              {t("login.titel")}
            </CardTitle>
            <CardDescription className="text-sm text-zinc-600">
              {t("login.beskrivelse")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form action={håndterSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">{t("login.email_label")}</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  placeholder={t("login.email_placeholder")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">{t("login.password_label")}</Label>
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
                {pending ? t("login.logger_ind") : t("login.log_ind_knap")}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
