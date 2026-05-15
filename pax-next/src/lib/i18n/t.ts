// Translation-helper. Bruges som t("login.titel") → "Log ind" (eller
// "Logg inn" hvis locale='no'). Fail-safe: hvis nøglen ikke findes i
// det valgte sprog, falder vi tilbage til dansk. Hvis den heller ikke
// findes der, returneres nøglen selv så devs ser hvad der mangler.
//
// Multi-file: dictionaries/$LOCALE/*.json deles op i namespace-filer
// (upload.json, analyse.json osv.) for at parallelisere oversættelses-
// arbejdet. Alle filer merges ved import-tid.

import type { Locale } from "./config";
import { DEFAULT_LOCALE } from "./config";

// Dansk er DEFAULT — ALLE keys SKAL findes her.
import da_base from "./dictionaries/da/_base.json";
import da_upload from "./dictionaries/da/upload.json";
import da_analyse from "./dictionaries/da/analyse.json";
import da_svarbrev from "./dictionaries/da/svarbrev.json";
import da_sager from "./dictionaries/da/sager.json";
import da_arkiv from "./dictionaries/da/arkiv.json";
import da_admin from "./dictionaries/da/admin.json";
import da_auth from "./dictionaries/da/auth.json";
import da_common from "./dictionaries/da/common.json";

// Norsk overlay — manglende keys falder tilbage til dansk via lookupNoegle.
import no_base from "./dictionaries/no/_base.json";
import no_upload from "./dictionaries/no/upload.json";
import no_analyse from "./dictionaries/no/analyse.json";
import no_svarbrev from "./dictionaries/no/svarbrev.json";
import no_sager from "./dictionaries/no/sager.json";
import no_arkiv from "./dictionaries/no/arkiv.json";
import no_admin from "./dictionaries/no/admin.json";
import no_auth from "./dictionaries/no/auth.json";
import no_common from "./dictionaries/no/common.json";

type Dict = Record<string, unknown>;

// Deep merge — senere keys overskriver tidligere på samme niveau.
// Bruges til at flette base + upload + analyse + ... til ét stort dict
// pr. locale.
function deepMerge(...dicts: Dict[]): Dict {
  const out: Dict = {};
  for (const d of dicts) {
    for (const k in d) {
      const v = d[k];
      if (
        typeof v === "object" &&
        v !== null &&
        !Array.isArray(v) &&
        typeof out[k] === "object" &&
        out[k] !== null
      ) {
        out[k] = deepMerge(out[k] as Dict, v as Dict);
      } else {
        out[k] = v;
      }
    }
  }
  return out;
}

const DICTS: Record<Locale, Dict> = {
  da: deepMerge(
    da_base as Dict,
    da_upload as Dict,
    da_analyse as Dict,
    da_svarbrev as Dict,
    da_sager as Dict,
    da_arkiv as Dict,
    da_admin as Dict,
    da_auth as Dict,
    da_common as Dict,
  ),
  no: deepMerge(
    no_base as Dict,
    no_upload as Dict,
    no_analyse as Dict,
    no_svarbrev as Dict,
    no_sager as Dict,
    no_arkiv as Dict,
    no_admin as Dict,
    no_auth as Dict,
    no_common as Dict,
  ),
  sv: {},
  de: {},
};

function lookupNoegle(dict: Dict, noegle: string): string | undefined {
  const dele = noegle.split(".");
  let cur: unknown = dict;
  for (const del of dele) {
    if (cur === null || cur === undefined) return undefined;
    if (typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[del];
  }
  return typeof cur === "string" ? cur : undefined;
}

function interpoler(streng: string, args?: Record<string, string | number>): string {
  if (!args) return streng;
  return streng.replace(/\{(\w+)\}/g, (match, navn) => {
    const v = args[navn];
    return v === undefined ? match : String(v);
  });
}

export function t(
  noegle: string,
  locale: Locale | null | undefined,
  args?: Record<string, string | number>,
): string {
  const aktivLocale: Locale = locale ?? DEFAULT_LOCALE;

  const dictForLocale = DICTS[aktivLocale];
  if (dictForLocale) {
    const v = lookupNoegle(dictForLocale, noegle);
    if (v !== undefined) return interpoler(v, args);
  }

  const v_da = lookupNoegle(DICTS.da, noegle);
  if (v_da !== undefined) return interpoler(v_da, args);

  return noegle;
}

export function lavT(locale: Locale | null | undefined) {
  return (noegle: string, args?: Record<string, string | number>) =>
    t(noegle, locale, args);
}
