import fs from "node:fs/promises";
import path from "node:path";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  TestSagDownloads,
  TestBrugereOversigt,
} from "@/components/admin/test-sager-admin";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import { lavT } from "@/lib/i18n/t";

type Kilde = "naevnet" | "klager" | "selskab";
type Fil = { navn: string; titel: string; kilde: Kilde };
type Sag = {
  mappe: string;
  sagsnr: string;
  indklagede: string;
  klager: string;
  destination: string;
  rejseperiode: string;
  antal_rejsende: string;
  rejse_pris: string;
  filer: Fil[];
};

type TestBruger = {
  slug: string;
  navn: string;
  by: string;
  sagsbehandler: string;
  email: string;
  fulde_navn: string;
  matchende_test_sag: string;
};

type TestBrugereConfig = {
  test_password: string;
  brugere: TestBruger[];
};

async function hentManifest(): Promise<Sag[]> {
  const manifestPath = path.join(
    process.cwd(),
    "public",
    "test-sager",
    "manifest.json",
  );
  try {
    const raw = await fs.readFile(manifestPath, "utf-8");
    return JSON.parse(raw) as Sag[];
  } catch {
    return [];
  }
}

async function hentTestBrugere(): Promise<TestBrugereConfig | null> {
  // Konfig ligger i repo-roden (over pax-next/). I dev og build kører
  // process.cwd() fra pax-next/, så vi går ét niveau op.
  const cfgPath = path.join(process.cwd(), "..", "test-brugere-config.json");
  try {
    const raw = await fs.readFile(cfgPath, "utf-8");
    return JSON.parse(raw) as TestBrugereConfig;
  } catch {
    return null;
  }
}

export default async function AdminTestSagerPage() {
  const [sager, testBrugere] = await Promise.all([
    hentManifest(),
    hentTestBrugere(),
  ]);

  // Hent locale fra aktuel bruger så server-rendered tekst er korrekt sprog
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const dbBruger = user ? await hentBrugerMedTenant(user.id) : null;
  const locale = dbBruger?.effektiv_sprog ?? "da";
  const t = lavT(locale);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">
            {t("admin.test_sager.kort_titel")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-zinc-600 leading-relaxed">
            {t("admin.test_sager.kort_beskrivelse_1", { antal: sager.length })}
          </p>
          <p className="text-sm text-zinc-600 leading-relaxed mt-2">
            {t("admin.test_sager.kort_beskrivelse_2")}
          </p>
        </CardContent>
      </Card>

      {testBrugere && <TestBrugereOversigt config={testBrugere} />}

      {sager.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-zinc-500">
            {t("admin.test_sager.ingen_test_sager_prefix")}{" "}
            <code className="bg-zinc-100 px-1 py-0.5 rounded text-xs">
              python3 scripts/generer_test_sager.py
            </code>{" "}
            {t("admin.test_sager.ingen_test_sager_suffix")}
          </CardContent>
        </Card>
      ) : (
        <TestSagDownloads sager={sager} />
      )}
    </div>
  );
}
