import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

// Loading-state for /sager/[id]. Vises mens server-componentet henter
// gemt sag + dekryptering. Mimicker det faktiske layout (header med
// titel + meta + en stak analyse-pillars) for at undgå layout-shift.
export default function GemtSagLoading() {
  return (
    <main className="flex flex-1 items-start justify-center bg-zinc-50 px-6 py-12">
      <div className="w-full max-w-4xl space-y-4">
        <div className="flex items-center justify-between">
          <Skeleton className="h-4 w-44" />
          <Skeleton className="h-9 w-24" />
        </div>
        <Card className="border-zinc-200 shadow-sm">
          <CardHeader className="space-y-2">
            <Skeleton className="h-8 w-2/3" />
            <Skeleton className="h-3 w-1/3" />
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Top-dashboard placeholders */}
            <div className="space-y-3">
              <Skeleton className="h-16 w-full rounded-md" />
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <Skeleton className="h-20 rounded-md" />
                <Skeleton className="h-20 rounded-md" />
                <Skeleton className="h-20 rounded-md" />
              </div>
            </div>
            {/* Pillar placeholders */}
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-32 w-full rounded-2xl" />
            ))}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
