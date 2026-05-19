/**
 * Tests for lib/api-client.ts.
 *
 * Verificerer at p-retry kun retry'er på 5xx + netværksfejl, at Zod-
 * validering fanger schema-mismatch (uden retry), og at ApiError
 * eksponerer status + detalje korrekt til kalderne.
 *
 * Vi mocker fetch globalt — ingen rigtige HTTP-kald.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { z } from "zod";

import {
  ApiError,
  postOgValider,
} from "@/lib/api-client";

// ─────────── Helpers ───────────

function fakeResponse(opts: {
  ok: boolean;
  status?: number;
  body?: unknown;
  bodyText?: string;
}): Response {
  const status = opts.status ?? (opts.ok ? 200 : 500);
  const bodyString =
    opts.body !== undefined ? JSON.stringify(opts.body) : (opts.bodyText ?? "");
  return new Response(bodyString, {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const testSchema = z.object({
  ok: z.literal(true),
  message: z.string(),
});

const fixedFormData = new FormData();
fixedFormData.append("dummy", "x");

// ─────────── Setup ───────────

beforeEach(() => {
  // p-retry's eksponentielle backoff (1s, 2s, 4s) ville gøre tests
  // langsomme. Vi bruger fake timers + auto-flushing så retries
  // sker øjeblikkeligt i test-tiden.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  process.env.NEXT_PUBLIC_API_URL = "http://test-api.local";
});

afterEach(() => {
  vi.useRealTimers();
  delete process.env.NEXT_PUBLIC_API_URL;
});

// ─────────── Success ───────────

describe("postOgValider — success path", () => {
  it("returnerer parsed data ved 200 OK med valid schema", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      fakeResponse({ ok: true, body: { ok: true, message: "hej" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await postOgValider("/api/test", testSchema, {
      formData: fixedFormData,
    });

    expect(result).toEqual({ ok: true, message: "hej" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("kalder den korrekte URL via NEXT_PUBLIC_API_URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      fakeResponse({ ok: true, body: { ok: true, message: "hej" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await postOgValider("/api/foerstevurdering", testSchema, {
      formData: fixedFormData,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://test-api.local/api/foerstevurdering",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

// ─────────── Retry på 5xx ───────────

describe("postOgValider — retry på 5xx", () => {
  it("retry'er på 503 indtil success", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(fakeResponse({ ok: false, status: 503, bodyText: "overloaded" }))
      .mockResolvedValueOnce(fakeResponse({ ok: false, status: 503, bodyText: "still overloaded" }))
      .mockResolvedValueOnce(fakeResponse({ ok: true, body: { ok: true, message: "endelig!" } }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await postOgValider("/api/test", testSchema, {
      formData: fixedFormData,
      retries: 3,
    });

    expect(result.message).toBe("endelig!");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("smider ApiError efter alle retries opbrugt", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      fakeResponse({ ok: false, status: 502, bodyText: "Bad Gateway" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      postOgValider("/api/test", testSchema, {
        formData: fixedFormData,
        retries: 2,
      }),
    ).rejects.toBeInstanceOf(ApiError);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("eksponerer status og detalje i ApiError", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      fakeResponse({ ok: false, status: 504, bodyText: "Gateway timeout fra Anthropic" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    try {
      await postOgValider("/api/test", testSchema, {
        formData: fixedFormData,
        retries: 1,
      });
      throw new Error("Forventede ApiError");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      const err = e as ApiError;
      expect(err.status).toBe(504);
      expect(err.detalje).toContain("Gateway timeout");
    }
  });
});

// ─────────── INGEN retry på 4xx ───────────

describe("postOgValider — INGEN retry på 4xx", () => {
  it("smider straks ved 400 uden at retry'e", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      fakeResponse({ ok: false, status: 400, bodyText: "Bad request" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      postOgValider("/api/test", testSchema, {
        formData: fixedFormData,
        retries: 5, // selv med 5 retries skal vi STOPPE ved 4xx
      }),
    ).rejects.toBeInstanceOf(ApiError);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("smider straks ved 422 (validation error)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      fakeResponse({ ok: false, status: 422, bodyText: "Invalid file format" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      postOgValider("/api/test", testSchema, {
        formData: fixedFormData,
        retries: 5,
      }),
    ).rejects.toMatchObject({ status: 422 });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("pakker FastAPI {detail: ...} ud så brugervenlig besked vises som message", async () => {
    // FastAPI's HTTPException returnerer altid {"detail": "..."} som
    // body. Vi vil have detail-strengen som message (besked) i UI'et,
    // ikke som raw JSON i detalje-feltet.
    const detailMsg =
      "Zip-filen er beskyttet med adgangskode. Pak filen ud manuelt og upload filerne enkeltvis.";
    const fetchMock = vi.fn().mockResolvedValue(
      fakeResponse({
        ok: false,
        status: 422,
        body: { detail: detailMsg },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    try {
      await postOgValider("/api/test", testSchema, {
        formData: fixedFormData,
        retries: 3,
      });
      throw new Error("Forventede ApiError");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      const err = e as ApiError;
      expect(err.status).toBe(422);
      expect(err.message).toBe(detailMsg);
      // detalje skal være tom — info'en er allerede i message
      expect(err.detalje).toBeUndefined();
    }
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("falder tilbage til raw text hvis body ikke er JSON", async () => {
    // Hvis backend returnerer plain text (ikke FastAPI-format), så
    // skal raw text bruges som detalje og message være den generiske
    // "API svarede N"-string.
    const fetchMock = vi.fn().mockResolvedValue(
      fakeResponse({ ok: false, status: 504, bodyText: "Gateway Timeout" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    try {
      await postOgValider("/api/test", testSchema, {
        formData: fixedFormData,
        retries: 1,
      });
      throw new Error("Forventede ApiError");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      const err = e as ApiError;
      expect(err.message).toBe("API svarede 504");
      expect(err.detalje).toContain("Gateway Timeout");
    }
  });
});

// ─────────── Schema-validering ───────────

describe("postOgValider — Zod-validering", () => {
  it("smider straks ved schema-mismatch (ingen retry)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      // body har ikke 'message'-feltet — schemaet kræver det
      fakeResponse({ ok: true, body: { ok: true } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      postOgValider("/api/test", testSchema, {
        formData: fixedFormData,
        retries: 5,
      }),
    ).rejects.toThrow(/respons matcher ikke forventet form/);

    // Schema-mismatch er programmer-fejl, ikke transient — INGEN retry
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("smider ved invalid JSON i response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      // response.ok=true men body er ikke JSON
      new Response("not json at all", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      postOgValider("/api/test", testSchema, {
        formData: fixedFormData,
        retries: 3,
      }),
    ).rejects.toThrow(/ugyldigt JSON/);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

// ─────────── Netværksfejl ───────────

describe("postOgValider — netværksfejl", () => {
  it("retry'er ved netværksfejl (TypeError fra fetch)", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("fetch failed"))
      .mockRejectedValueOnce(new TypeError("fetch failed"))
      .mockResolvedValueOnce(
        fakeResponse({ ok: true, body: { ok: true, message: "tilbage online" } }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const result = await postOgValider("/api/test", testSchema, {
      formData: fixedFormData,
      retries: 3,
    });

    expect(result.message).toBe("tilbage online");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("smider ApiError hvis alle netværks-retries opbrugt", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValue(new TypeError("DNS lookup failed"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      postOgValider("/api/test", testSchema, {
        formData: fixedFormData,
        retries: 2,
      }),
    ).rejects.toThrow(/Forbindelsen til serveren blev kortvarigt afbrudt/);
  });

  it("inkluderer endpoint-sti i tekniske detalje", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValue(new TypeError("DNS lookup failed"));
    vi.stubGlobal("fetch", fetchMock);

    try {
      await postOgValider("/api/test", testSchema, {
        formData: fixedFormData,
        retries: 1,
      });
      throw new Error("forventet exception ikke kastet");
    } catch (e) {
      // ApiError.detalje skal indeholde endpoint-stien så admin kan
      // se hvor fejlen kom fra (gemt bag "Tekniske detaljer"-expander).
      const err = e as { detalje?: string };
      expect(err.detalje).toContain("/api/test");
    }
  });
});

// ─────────── Konfiguration ───────────

describe("postOgValider — konfigurationsfejl", () => {
  it("returnerer fejl hvis NEXT_PUBLIC_API_URL ikke er sat", async () => {
    delete process.env.NEXT_PUBLIC_API_URL;
    // Når base-URL ikke er sat, ramler fetch fordi den prøver at
    // bygge URL'en mod ren path. Vi tester at vi får en venlig fejl
    // (ikke en uventet TypeError).
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Invalid URL"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      postOgValider("/api/test", testSchema, {
        formData: fixedFormData,
        retries: 1,
      }),
    ).rejects.toThrow(/Forbindelsen til serveren blev kortvarigt afbrudt/);
  });
});
