import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { UploadForm } from "@/components/upload-form";
import Link from "next/link";

// Server Component — proxy.ts har allerede beskyttet ruten med
// auth-redirect, så vi ved brugeren er logget ind.
export default function NySagPage() {
  return (
    <main className="flex flex-1 items-start justify-center bg-zinc-50 px-6 py-12">
      <div className="w-full max-w-2xl space-y-4">
        <div className="flex items-center justify-between">
          <Link
            href="/"
            className="text-sm text-zinc-500 hover:text-zinc-900 underline-offset-4 hover:underline"
          >
            ← Tilbage til forsiden
          </Link>
          <Link
            href="/"
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            Forside
          </Link>
        </div>

        <Card className="border-zinc-200 shadow-sm">
          <CardHeader className="space-y-2">
            <CardTitle className="text-2xl font-semibold tracking-tight">
              Upload klage + bilag
            </CardTitle>
            <CardDescription className="text-zinc-600">
              Træk filer ind, eller klik for at vælge. PDF, DOCX, PNG, JPG
              understøttes. Filerne sendes til FastAPI-broen som bruger den
              eksisterende <code>processor.py</code> til at læse indholdet.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <UploadForm />
          </CardContent>
        </Card>

        <p className="text-xs text-zinc-500 text-center italic">
          Step 6 af migrationen: kun upload + parse, ingen DB-write endnu.
          Filerne forsvinder når du forlader siden.
        </p>
      </div>
    </main>
  );
}
