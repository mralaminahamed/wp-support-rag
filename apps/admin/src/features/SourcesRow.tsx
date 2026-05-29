// Expandable per-plugin sources detail. Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import { listSources } from "@/api/admin";
import { Badge } from "@/components/ui/badge";
import { ErrorState, Skeleton } from "@/components/ui/feedback";
import { extractErrorMessage } from "@/lib/queryClient";
import { relativeTime } from "@/lib/utils";

export function SourcesRow({ slug, colSpan }: { slug: string; colSpan: number }) {
  const sources = useQuery({
    queryKey: ["sources", slug],
    queryFn: () => listSources(slug),
  });

  return (
    <tr>
      <td colSpan={colSpan} className="bg-surface-2">
        {sources.isLoading ? (
          <Skeleton className="h-5 w-72" />
        ) : sources.isError ? (
          <ErrorState message={extractErrorMessage(sources.error)} />
        ) : (
          <div className="flex flex-wrap gap-2">
            {sources.data!.map((s) => (
              <Badge key={s.source_type} tone={s.enabled ? "accent" : "neutral"}>
                <span className="font-mono">{s.source_type}</span>
                <span className="opacity-70">· {relativeTime(s.last_ingested_at)}</span>
              </Badge>
            ))}
            {sources.data!.length === 0 && <span className="text-sm text-muted">No sources.</span>}
          </div>
        )}
      </td>
    </tr>
  );
}
