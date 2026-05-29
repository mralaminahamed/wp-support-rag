// Expandable per-plugin sources detail. Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import { listSources } from "@/api/admin";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/ui/feedback";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { relativeTime } from "@/lib/format";
import { extractErrorMessage } from "@/lib/queryClient";

export function SourcesRow({ slug, colSpan }: { slug: string; colSpan: number }) {
  const sources = useQuery({
    queryKey: ["sources", slug],
    queryFn: () => listSources(slug),
  });

  return (
    <TableRow>
      <TableCell colSpan={colSpan} className="bg-muted/40">
        {sources.isLoading ? (
          <Skeleton className="h-5 w-72" />
        ) : sources.isError ? (
          <ErrorState message={extractErrorMessage(sources.error)} />
        ) : sources.data!.length === 0 ? (
          <span className="text-sm text-muted-foreground">No sources.</span>
        ) : (
          <div className="flex flex-wrap gap-2 whitespace-normal">
            {sources.data!.map((s) => (
              <Badge key={s.source_type} variant={s.enabled ? "accent" : "secondary"}>
                <span className="font-mono">{s.source_type}</span>
                <span className="opacity-70">· {relativeTime(s.last_ingested_at)}</span>
              </Badge>
            ))}
          </div>
        )}
      </TableCell>
    </TableRow>
  );
}
