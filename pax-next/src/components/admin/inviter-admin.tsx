"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import {
  inviterBrugerAction,
  opretBrugerMedTempPasswordAction,
} from "@/app/admin/actions";
import type { Tenant } from "@/lib/queries/tenants";
import { useT } from "@/lib/i18n/client";

type Metode = "email" | "temp";

export function InviterAdmin({ tenants }: { tenants: Tenant[] }) {
  const t = useT();
  const [pending, startTransition] = useTransition();
  const [email, sætEmail] = useState("");
  const [navn, sætNavn] = useState("");
  const [tenantId, sætTenantId] = useState<number | "">(
    tenants[0]?.id ?? "",
  );
  const [role, sætRole] = useState<"jurist" | "admin">("jurist");
  const [metode, sætMetode] = useState<Metode>("email");

  const [tempPassword, sætTempPassword] = useState<{
    email: string;
    pw: string;
  } | null>(null);

  function nulstil() {
    sætEmail("");
    sætNavn("");
    sætTenantId(tenants[0]?.id ?? "");
    sætRole("jurist");
  }

  function send() {
    if (!email.trim()) {
      toast.error(t("admin.inviter.toast_email_paakraevet"));
      return;
    }
    if (!tenantId) {
      toast.error(t("admin.inviter.toast_vaelg_selskab"));
      return;
    }
    sætTempPassword(null);
    startTransition(async () => {
      if (metode === "email") {
        const r = await inviterBrugerAction({
          email,
          tenantId: Number(tenantId),
          role,
          fuldeNavn: navn,
        });
        if (r.ok) {
          toast.success(
            r.data?.besked
              ? r.data.besked
              : t("admin.inviter.toast_invitation_sendt", { email }),
          );
          nulstil();
        } else {
          toast.error(r.fejl);
        }
      } else {
        const r = await opretBrugerMedTempPasswordAction({
          email,
          tenantId: Number(tenantId),
          role,
          fuldeNavn: navn,
        });
        if (r.ok) {
          toast.success(t("admin.inviter.toast_bruger_oprettet", { email }));
          sætTempPassword({ email, pw: r.data!.tempPassword });
          nulstil();
        } else {
          toast.error(r.fejl);
        }
      }
    });
  }

  if (tenants.length === 0) {
    return (
      <Card>
        <CardContent className="py-6">
          <p className="text-sm text-amber-700">
            {t("admin.inviter.skal_oprette_tenant")}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">
            {t("admin.inviter.titel")}
          </CardTitle>
          <CardDescription className="text-xs">
            {t("admin.inviter.beskrivelse")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>{t("admin.inviter.felt_email")}</Label>
              <Input
                value={email}
                onChange={(e) => sætEmail(e.target.value)}
                placeholder={t("admin.inviter.felt_email_placeholder")}
                disabled={pending}
                type="email"
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("admin.inviter.felt_navn")}</Label>
              <Input
                value={navn}
                onChange={(e) => sætNavn(e.target.value)}
                placeholder={t("admin.inviter.felt_navn_placeholder")}
                disabled={pending}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("admin.inviter.felt_tenant")}</Label>
              <select
                value={tenantId}
                onChange={(e) => sætTenantId(Number(e.target.value))}
                disabled={pending}
                className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
              >
                {tenants.map((tenant) => (
                  <option key={tenant.id} value={tenant.id}>
                    {tenant.navn} ({tenant.slug})
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>{t("admin.inviter.felt_rolle")}</Label>
              <div className="flex gap-2">
                <RoleKnap
                  aktiv={role === "jurist"}
                  onClick={() => sætRole("jurist")}
                  disabled={pending}
                >
                  {t("admin.inviter.rolle_jurist")}
                </RoleKnap>
                <RoleKnap
                  aktiv={role === "admin"}
                  onClick={() => sætRole("admin")}
                  disabled={pending}
                >
                  {t("admin.inviter.rolle_admin")}
                </RoleKnap>
              </div>
            </div>
          </div>

          <div className="space-y-2 pt-2 border-t border-zinc-200">
            <Label>{t("admin.inviter.felt_metode")}</Label>
            <div className="space-y-2">
              <MetodeRadio
                aktiv={metode === "email"}
                onClick={() => sætMetode("email")}
                disabled={pending}
                titel={t("admin.inviter.metode_email_titel")}
                hjælp={t("admin.inviter.metode_email_hjaelp")}
              />
              <MetodeRadio
                aktiv={metode === "temp"}
                onClick={() => sætMetode("temp")}
                disabled={pending}
                titel={t("admin.inviter.metode_temp_titel")}
                hjælp={t("admin.inviter.metode_temp_hjaelp")}
              />
            </div>
          </div>

          <Button
            type="button"
            onClick={send}
            disabled={pending || !email.trim() || !tenantId}
            className="w-full"
          >
            {pending
              ? t("admin.inviter.knap_sender")
              : metode === "email"
                ? t("admin.inviter.knap_send_invitation")
                : t("admin.inviter.knap_opret_temp")}
          </Button>
        </CardContent>
      </Card>

      {tempPassword && (
        <Card className="border-amber-300 bg-amber-50">
          <CardHeader>
            <CardTitle className="text-sm font-semibold text-amber-900">
              {t("admin.inviter.credentials_titel")}
            </CardTitle>
            <CardDescription className="text-xs text-amber-800">
              {t("admin.inviter.credentials_beskrivelse")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="rounded-md bg-white border border-amber-200 px-4 py-3 text-sm font-mono">
              {`${t("admin.inviter.credentials_email")}:    ${tempPassword.email}\n${t("admin.inviter.credentials_password")}: ${tempPassword.pw}`}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function RoleKnap({
  aktiv,
  onClick,
  disabled,
  children,
}: {
  aktiv: boolean;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
        aktiv
          ? "border-zinc-900 bg-zinc-900 text-white"
          : "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50"
      }`}
    >
      {children}
    </button>
  );
}

function MetodeRadio({
  aktiv,
  onClick,
  disabled,
  titel,
  hjælp,
}: {
  aktiv: boolean;
  onClick: () => void;
  disabled?: boolean;
  titel: string;
  hjælp: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`w-full text-left rounded-md border px-4 py-3 transition-colors disabled:opacity-50 ${
        aktiv
          ? "border-zinc-900 bg-zinc-50"
          : "border-zinc-200 bg-white hover:bg-zinc-50"
      }`}
    >
      <p className="text-sm font-medium">{titel}</p>
      <p className="text-xs text-zinc-500 mt-0.5">{hjælp}</p>
    </button>
  );
}
