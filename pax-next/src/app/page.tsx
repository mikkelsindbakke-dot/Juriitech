import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function Home() {
  return (
    <main className="flex flex-1 items-center justify-center bg-zinc-50 px-6 py-20">
      <Card className="w-full max-w-xl border-zinc-200 shadow-sm">
        <CardHeader className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-3 w-3 rounded-full bg-amber-500" />
            <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Migrations-version · ikke i produktion
            </span>
          </div>
          <CardTitle className="text-3xl font-semibold tracking-tight">
            juriitech PAX
          </CardTitle>
          <CardDescription className="text-base text-zinc-600">
            Next.js-version af PAX, bygget parallelt med den nuværende Streamlit-app.
            Indtil cutover lever den kun lokalt og påvirker ikke kunder.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-zinc-700">
          <div className="rounded-md bg-zinc-100 p-4 leading-relaxed">
            <p className="font-medium text-zinc-900 mb-2">Status</p>
            <ul className="space-y-1.5">
              <li>✓ Next.js 16 + TypeScript + Tailwind v4 + App Router</li>
              <li>✓ shadcn/ui (neutral palette)</li>
              <li>✓ Space Grotesk font</li>
              <li>· Supabase Auth — ikke koblet endnu</li>
              <li>· FastAPI-bro til ai_engine.py — ikke bygget endnu</li>
            </ul>
          </div>
          <p className="text-zinc-500 italic">
            Den nuværende PAX kører fortsat på{" "}
            <a
              href="https://pax.juriitech.com"
              className="underline underline-offset-2 hover:text-zinc-900"
              target="_blank"
              rel="noopener noreferrer"
            >
              pax.juriitech.com
            </a>{" "}
            — kunder mærker intet før vi er klar.
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
