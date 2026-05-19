// Catch-all proxy for /api/* → intern uvicorn (FastAPI på 127.0.0.1:8000).
//
// To problemer denne proxy løser:
//
// 1. Long-poll keep-alive
//    Fly's edge proxy lukker forbindelser efter ~60 sek uden data. AI-
//    kald (foerstevurdering, tjekliste, svarbrev) tager 30-90 sek hvor
//    INTET data flyder før det færdige svar. Vi sender derfor en
//    space-byte hver 5. sek mens FastAPI arbejder. JSON-parsere
//    ignorerer leading whitespace, så det færdige body parses som
//    forventet på frontend.
//
//    Når upstream svarer NON-200, embedder vi den oprindelige status i
//    body som `_proxy_status` så frontend stadig kan reagere korrekt
//    (vi kan ikke ændre HTTP status code efter streaming er begyndt).
//
// 2. Body-streaming
//    Næste lag fra Fly proxy ind i Node ville eller cleare requests
//    >30s (undici default). Med duplex:'half' og runtime:'nodejs' sætter
//    vi os over det.
//
// Lokal dev rammer denne route IKKE — frontenden kalder direkte
// http://localhost:8000 (NEXT_PUBLIC_API_URL i .env.local).

import { NextRequest } from "next/server";
import * as Sentry from "@sentry/nextjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const UVICORN_URL = "http://127.0.0.1:8000";

// Rapporter en api-proxy-fejl til Sentry MED kontekst. Vi bruger
// `Sentry.captureException` i stedet for `console.error` så fejlene
// faktisk lander i pax-next-projektet og ikke kun i Fly logs.
function rapportérTilSentry(
  e: unknown,
  ctx: {
    method: string;
    url: string;
    path: string;
    tekniskDetalje: string;
    lag: "tidlig-fejl" | "stream-fejl" | "passthrough-fejl";
  },
) {
  try {
    Sentry.withScope((scope) => {
      scope.setTag("source", "api-proxy");
      scope.setTag("upstream_lag", ctx.lag);
      scope.setTag("upstream_path", ctx.path);
      scope.setContext("api-proxy", {
        method: ctx.method,
        upstream_url: ctx.url,
        upstream_lag: ctx.lag,
        teknisk_detalje: ctx.tekniskDetalje,
      });
      scope.setLevel("error");
      if (e instanceof Error) {
        Sentry.captureException(e);
      } else {
        Sentry.captureMessage(
          `api-proxy ${ctx.lag}: ${ctx.tekniskDetalje.slice(0, 200)}`,
          "error",
        );
      }
    });
  } catch (sentryErr) {
    console.error("[api-proxy] Sentry-rapport fejlede:", sentryErr);
  }
}

// Endpoints der typisk tager > 30 sekunder. For disse aktiverer vi
// heartbeat-keep-alive. For korte endpoints (sagsmetadata, parse-fil,
// admin/audit-log, auth/*) sender vi direkte gennem — sparer overhead.
const LANGE_ENDPOINTS = new Set<string>([
  "foerstevurdering",
  "svarbrev",
  "tjekliste",
  "anonymiser",
]);

function erLangEndpoint(pathParts: string[]): boolean {
  return pathParts.length > 0 && LANGE_ENDPOINTS.has(pathParts[0]);
}

async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await params;
  const url = `${UVICORN_URL}/api/${path.join("/")}${request.nextUrl.search}`;

  // Headers gennem-passes. Hop-by-hop headers og host fjernes.
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("transfer-encoding");

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    duplex: "half",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
  }

  // Korte endpoints: direkte passthrough — ingen heartbeat-overhead.
  if (!erLangEndpoint(path)) {
    return korresPassthrough(url, init, request.method);
  }

  // Lange endpoints: race mod 50-sek deadline. Hvis upstream svarer
  // før, returner normalt. Hvis ikke, fortsæt med heartbeat-streaming.
  return langKaldMedHeartbeat(url, init, request.method);
}

async function korresPassthrough(
  url: string,
  init: RequestInit & { duplex?: "half" },
  method: string,
): Promise<Response> {
  try {
    const upstream = await fetch(url, init);
    const responseHeaders = new Headers(upstream.headers);
    responseHeaders.delete("connection");
    responseHeaders.delete("transfer-encoding");
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch (e) {
    const tekniskDetalje = e instanceof Error ? e.message : String(e);
    console.error(`[api-proxy] ${method} ${url} fejlede:`, tekniskDetalje);
    rapportérTilSentry(e, {
      method,
      url,
      path: new URL(url).pathname,
      tekniskDetalje,
      lag: "passthrough-fejl",
    });
    return Response.json(
      {
        detail:
          "Forbindelsen til serveren blev kortvarigt afbrudt. Prøv igen om et øjeblik.",
      },
      { status: 503 },
    );
  }
}

async function langKaldMedHeartbeat(
  url: string,
  init: RequestInit & { duplex?: "half" },
  method: string,
): Promise<Response> {
  // Start fetch — vi await'er ikke direkte fordi vi vil starte heartbeat
  // samtidig.
  const upstreamPromise = fetch(url, init).then(
    (res) => ({ ok: true as const, res }),
    (err) => ({ ok: false as const, err }),
  );

  // Race: hvis upstream svarer inden RACE_DEADLINE_MS, returner normalt.
  // Ellers fortsætter vi med streaming + heartbeat.
  const RACE_DEADLINE_MS = 30_000;
  let hurtigSvar:
    | { ok: true; res: Response }
    | { ok: false; err: unknown }
    | null = null;

  await new Promise<void>((resolve) => {
    const t = setTimeout(resolve, RACE_DEADLINE_MS);
    upstreamPromise.then((result) => {
      hurtigSvar = result;
      clearTimeout(t);
      resolve();
    });
  });

  // Hurtigt svar inden deadline → returner direkte med korrekt status.
  if (hurtigSvar !== null) {
    const r = hurtigSvar as
      | { ok: true; res: Response }
      | { ok: false; err: unknown };
    if (r.ok) {
      const responseHeaders = new Headers(r.res.headers);
      responseHeaders.delete("connection");
      responseHeaders.delete("transfer-encoding");
      return new Response(r.res.body, {
        status: r.res.status,
        statusText: r.res.statusText,
        headers: responseHeaders,
      });
    }
    // Tidlig fejl — typisk netværks-fejl mod localhost FastAPI.
    const tekniskDetalje =
      r.err instanceof Error ? r.err.message : String(r.err);
    console.error(`[api-proxy] ${method} ${url} fejlede tidligt:`, tekniskDetalje);
    rapportérTilSentry(r.err, {
      method,
      url,
      path: new URL(url).pathname,
      tekniskDetalje,
      lag: "tidlig-fejl",
    });
    return Response.json(
      {
        detail:
          "Forbindelsen til serveren blev kortvarigt afbrudt. Prøv igen om et øjeblik.",
      },
      { status: 503 },
    );
  }

  // Stadig undervejs → start streaming response med heartbeats.
  // Bemærk: vi returnerer 200 her uanset upstream-status. Den faktiske
  // status embedder vi som _proxy_status i body, som api-client.ts
  // tjekker for og re-eskalerer korrekt.
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      // Første space — sikrer at Fly proxy ser at vi er aktive.
      controller.enqueue(encoder.encode(" "));

      // Heartbeat hver 5 sek så Fly proxy ikke timer ud.
      const intervalId = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(" "));
        } catch {
          // Controller lukket — stop heartbeating
          clearInterval(intervalId);
        }
      }, 5_000);

      try {
        const result = await upstreamPromise;
        clearInterval(intervalId);

        if (!result.ok) {
          const tekniskDetalje =
            result.err instanceof Error
              ? result.err.message
              : String(result.err);
          console.error(`[api-proxy] ${method} ${url} fejlede:`, tekniskDetalje);
          rapportérTilSentry(result.err, {
            method,
            url,
            path: new URL(url).pathname,
            tekniskDetalje,
            lag: "stream-fejl",
          });
          controller.enqueue(
            encoder.encode(
              JSON.stringify({
                detail:
                  "Forbindelsen til serveren blev kortvarigt afbrudt. Prøv igen om et øjeblik.",
                _proxy_status: 503,
              }),
            ),
          );
          controller.close();
          return;
        }

        const upstream = result.res;

        if (upstream.status === 200) {
          // Stream body verbatim — JSON-parser på frontend ignorerer
          // de leading space-heartbeats.
          const reader = upstream.body?.getReader();
          if (reader) {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              if (value) controller.enqueue(value);
            }
          }
          controller.close();
          return;
        }

        // Non-200: parse body som JSON og inject _proxy_status så
        // frontend kan eskalere det rigtigt.
        const bodyText = await upstream.text();
        let bodyJson: Record<string, unknown> = {};
        try {
          bodyJson = JSON.parse(bodyText);
        } catch {
          bodyJson = { detail: bodyText.slice(0, 500) };
        }
        bodyJson._proxy_status = upstream.status;
        controller.enqueue(encoder.encode(JSON.stringify(bodyJson)));
        controller.close();
      } catch (e) {
        clearInterval(intervalId);
        const tekniskDetalje = e instanceof Error ? e.message : String(e);
        console.error(`[api-proxy] ${method} ${url} stream fejlede:`, tekniskDetalje);
        rapportérTilSentry(e, {
          method,
          url,
          path: new URL(url).pathname,
          tekniskDetalje,
          lag: "stream-fejl",
        });
        try {
          controller.enqueue(
            encoder.encode(
              JSON.stringify({
                detail:
                  "Forbindelsen til serveren blev kortvarigt afbrudt. Prøv igen om et øjeblik.",
                _proxy_status: 503,
              }),
            ),
          );
          controller.close();
        } catch {
          // Allerede lukket
        }
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
