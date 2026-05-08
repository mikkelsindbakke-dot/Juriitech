import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/server";
import { logout } from "./login/actions";

// Server Component — kører server-side ved hver request.
// proxy.ts har allerede verificeret at brugeren er logget ind når
// vi når hertil; vi kan derfor antage at user findes.
export default async function Home() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

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
            Logget ind som <strong>{user?.email}</strong>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-zinc-700">
          <div className="rounded-md bg-zinc-100 p-4 leading-relaxed">
            <p className="font-medium text-zinc-900 mb-2">Status</p>
            <ul className="space-y-1.5">
              <li>✓ Next.js 16 + TypeScript + Tailwind v4 + App Router</li>
              <li>✓ shadcn/ui (neutral palette)</li>
              <li>✓ Space Grotesk font</li>
              <li>✓ Supabase Auth — du er logget ind</li>
              <li>· Tenant-opslag — kommer i step 4</li>
              <li>· FastAPI-bro til ai_engine.py — kommer i step 5</li>
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
          <form action={logout}>
            <Button type="submit" variant="outline" size="sm">
              Log ud
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
