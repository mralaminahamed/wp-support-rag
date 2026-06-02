// Expandable per-plugin sources detail with ingestion run stats. Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import { listSources } from "@/api/admin";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/ui/feedback";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { relativeTime } from "@/lib/format";
import { extractErrorMessage } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import type { SourceSummary } from "@/types/api";

const RUN_STYLE: Record<string, { cls: string; icon: string; label: string }> = {
  queued:    { cls: "bg-warning/10 text-warning border-warning/20",         icon: "ti-clock",         label: "queued"    },
  running:   { cls: "bg-primary/10 text-primary border-primary/20",         icon: "ti-loader-2",      label: "running"   },
  succeeded: { cls: "bg-success/10 text-success border-success/20",         icon: "ti-circle-check",  label: "succeeded" },
  failed:    { cls: "bg-destructive/10 text-destructive border-destructive/20", icon: "ti-alert-circle", label: "failed" },
};

function RunStatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-xs text-muted-foreground">—</span>;
  const cfg = RUN_STYLE[status] ?? { cls: "bg-muted text-muted-foreground border-border", icon: "ti-point", label: status };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        cfg.cls,
      )}
    >
      <i className={cn(`ti ${cfg.icon} text-[10px]`, status === "running" && "animate-spin")} />
      {cfg.label}
    </span>
  );
}

const ACTIVE_STATUSES = new Set(["queued", "running"]);

function SourceCard({ s }: { s: SourceSummary }) {
  return (
    <div className="rounded-lg border border-border bg-background p-3 space-y-2 min-w-[220px]">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[12px] font-medium text-foreground">{s.source_type}</span>
        <Badge variant={s.enabled ? "accent" : "secondary"} className="text-[10px]">
          {s.enabled ? "enabled" : "disabled"}
        </Badge>
      </div>

      {/* Last ingested */}
      <div className="text-[11px] text-muted-foreground">
        <i className="ti ti-clock mr-1" />
        {s.last_ingested_at ? relativeTime(s.last_ingested_at) : "never ingested"}
      </div>

      {/* Last run stats */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <RunStatusBadge status={s.run_status} />
        {s.run_chunks !== null && (
          <span className="text-[11px] text-muted-foreground">
            <i className="ti ti-stack-2 mr-0.5" />
            {s.run_chunks.toLocaleString()} chunks
          </span>
        )}
        {s.run_docs !== null && (
          <span className="text-[11px] text-muted-foreground">
            <i className="ti ti-files mr-0.5" />
            {s.run_docs.toLocaleString()} docs
          </span>
        )}
        {s.run_finished_at && (
          <span className="text-[11px] text-muted-foreground">
            · {relativeTime(s.run_finished_at)}
          </span>
        )}
      </div>

      {/* Error */}
      {s.run_error && (
        <p className="rounded border border-destructive/20 bg-destructive/5 px-2 py-1 text-[11px] text-destructive line-clamp-2">
          <i className="ti ti-alert-triangle mr-1" />
          {s.run_error}
        </p>
      )}
    </div>
  );
}

export function SourcesRow({ slug, colSpan }: { slug: string; colSpan: number }) {
  const sources = useQuery({
    queryKey: ["sources", slug],
    queryFn: () => listSources(slug),
    // Poll every 3 s while any source has an active run
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      return data.some((s) => s.run_status && ACTIVE_STATUSES.has(s.run_status)) ? 3000 : false;
    },
  });

  return (
    <TableRow>
      <TableCell colSpan={colSpan} className="bg-muted/40 py-3">
        {sources.isLoading ? (
          <div className="flex gap-2">
            <Skeleton className="h-24 w-52" />
            <Skeleton className="h-24 w-52" />
          </div>
        ) : sources.isError ? (
          <ErrorState message={extractErrorMessage(sources.error)} />
        ) : sources.data!.length === 0 ? (
          <span className="text-sm text-muted-foreground">No sources.</span>
        ) : (
          <div className="flex flex-wrap gap-2">
            {sources.data!.map((s) => (
              <SourceCard key={s.source_type} s={s} />
            ))}
          </div>
        )}
      </TableCell>
    </TableRow>
  );
}
