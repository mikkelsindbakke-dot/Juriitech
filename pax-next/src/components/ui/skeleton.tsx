// Tailwind-baseret skeleton-primitive. Standardklassen 'animate-pulse'
// giver den karakteristiske blink-loop. Konfigurerbar via className så
// kalderne kan styre størrelse og form.
//
// Brug via composition:
//   <Skeleton className="h-4 w-3/4" />   // tekst-linje
//   <Skeleton className="h-32 w-full" /> // billed-/kort-pladsholder
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-zinc-200/70", className)}
      {...props}
    />
  );
}
