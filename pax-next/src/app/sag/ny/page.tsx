import { buttonVariants } from "@/components/ui/button";
import { UploadForm } from "@/components/upload-form";
import Link from "next/link";

export default function NySagPage() {
  return (
    <main className="flex-1 bg-zinc-50 px-6 py-10">
      <div className="mx-auto w-full max-w-6xl space-y-6">
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

        <header className="space-y-2">
          <h1 className="font-serif text-4xl sm:text-5xl font-bold tracking-tight text-zinc-900">
            Ny sag
          </h1>
          <p className="text-zinc-600 max-w-3xl">
            Upload klage og bilag (PDF, DOCX, PNG, JPG eller ZIP). juriitech
            PAX kører en grundig analyse, finder præcedens i Pakkerejse-
            Ankenævnets afgørelser og hjælper dig hele vejen til et
            færdigt svarbrev.
          </p>
        </header>

        <UploadForm />
      </div>
    </main>
  );
}
