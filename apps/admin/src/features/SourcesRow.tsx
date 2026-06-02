// Expandable per-plugin sources table: enable/disable, per-source ingest, delete, add. Author: Al Amin Ahamed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { addSource, deleteSource, ingestSource, listSources, patchSource } from "@/api/admin";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/feedback";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { relativeTime } from "@/lib/format";
import { extractErrorMessage } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import { SOURCE_TYPES } from "@/types/api";
import type { SourceSummary } from "@/types/api";

const RUN_STYLE: Record<string, { cls: string; icon: string; label: string }> = {
  queued:    { cls: "bg-warning/10 text-warning border-warning/20",               icon: "ti-clock",        label: "queued"    },
  running:   { cls: "bg-primary/10 text-primary border-primary/20",               icon: "ti-loader-2",     label: "running"   },
  succeeded: { cls: "bg-success/10 text-success border-success/20",               icon: "ti-circle-check", label: "succeeded" },
  failed:    { cls: "bg-destructive/10 text-destructive border-destructive/20",   icon: "ti-alert-circle", label: "failed"    },
};

function RunStatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-xs text-muted-foreground">—</span>;
  const cfg = RUN_STYLE[status] ?? {
    cls: "bg-muted text-muted-foreground border-border",
    icon: "ti-point",
    label: status,
  };
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

function EnableToggle({
  enabled,
  loading,
  onToggle,
}: {
  enabled: boolean;
  loading: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={loading}
      aria-label={enabled ? "Disable source" : "Enable source"}
      className={cn(
        "relative inline-flex h-4 w-7 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        enabled ? "bg-success" : "bg-muted-foreground/40",
      )}
    >
      <span
        className={cn(
          "pointer-events-none block h-3 w-3 rounded-full bg-white shadow-sm transition-transform",
          enabled ? "translate-x-3" : "translate-x-0",
        )}
      />
    </button>
  );
}

const ACTIVE_STATUSES = new Set(["queued", "running"]);

function SourceTableRow({
  s,
  onToggle,
  onIngest,
  onDelete,
  toggleLoading,
  ingestLoading,
  deleteLoading,
}: {
  s: SourceSummary;
  onToggle: (sourceType: string, enabled: boolean) => void;
  onIngest: (sourceType: string) => void;
  onDelete: (sourceType: string) => void;
  toggleLoading: boolean;
  ingestLoading: boolean;
  deleteLoading: boolean;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <tr className="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors">
      {/* Source type */}
      <td className="py-2.5 pl-4 pr-3">
        <span className="font-mono text-[12px] font-medium text-foreground">{s.source_type}</span>
      </td>

      {/* Enabled toggle */}
      <td className="pr-3">
        <EnableToggle
          enabled={s.enabled}
          loading={toggleLoading}
          onToggle={() => onToggle(s.source_type, !s.enabled)}
        />
      </td>

      {/* Run status */}
      <td className="pr-3">
        <div className="flex flex-col gap-0.5">
          <RunStatusBadge status={s.run_status} />
          {s.run_error && (
            <p
              className="max-w-[200px] truncate text-[10px] text-destructive"
              title={s.run_error}
            >
              {s.run_error}
            </p>
          )}
        </div>
      </td>

      {/* Last ingested */}
      <td className="pr-3 text-[12px] text-muted-foreground whitespace-nowrap">
        {s.last_ingested_at ? relativeTime(s.last_ingested_at) : "never"}
      </td>

      {/* Chunks */}
      <td className="pr-3 text-[12px] text-muted-foreground">
        {s.run_chunks !== null ? (
          <Badge variant={s.run_chunks > 0 ? "accent" : "secondary"} className="text-[10px]">
            {s.run_chunks.toLocaleString()}
          </Badge>
        ) : (
          <span>—</span>
        )}
      </td>

      {/* Docs */}
      <td className="pr-3 text-[12px] text-muted-foreground">
        {s.run_docs !== null ? s.run_docs.toLocaleString() : "—"}
      </td>

      {/* Actions */}
      <td className="pr-3 text-right">
        {confirmDelete ? (
          <span className="inline-flex items-center gap-1.5 text-[11px]">
            <span className="text-destructive font-medium">Delete?</span>
            <button
              type="button"
              onClick={() => { onDelete(s.source_type); setConfirmDelete(false); }}
              disabled={deleteLoading}
              className="text-destructive font-semibold hover:underline disabled:opacity-50"
            >
              Yes
            </button>
            <button
              type="button"
              onClick={() => setConfirmDelete(false)}
              className="text-muted-foreground hover:underline"
            >
              No
            </button>
          </span>
        ) : (
          <span className="inline-flex items-center gap-0.5">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onIngest(s.source_type)}
              disabled={ingestLoading}
              title="Trigger ingest for this source"
              className="h-7 w-7 p-0"
            >
              <i className="ti ti-player-play text-[12px]" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmDelete(true)}
              title="Delete this source"
              className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
            >
              <i className="ti ti-trash text-[12px]" />
            </Button>
          </span>
        )}
      </td>
    </tr>
  );
}

function AddSourceRow({
  usedTypes,
  onAdd,
  loading,
}: {
  usedTypes: Set<string>;
  onAdd: (sourceType: string) => void;
  loading: boolean;
}) {
  const available = SOURCE_TYPES.filter((t) => !usedTypes.has(t));
  const [selected, setSelected] = useState(available[0] ?? "");

  if (available.length === 0) return null;

  return (
    <tr>
      <td colSpan={7} className="px-4 py-2">
        <div className="flex items-center gap-2">
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="h-7 rounded border border-border bg-background px-2 text-[12px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {available.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onAdd(selected)}
            disabled={loading || !selected}
            className="h-7 text-[12px]"
          >
            <i className="ti ti-plus text-[11px] mr-1" />
            Add source
          </Button>
        </div>
      </td>
    </tr>
  );
}

export function SourcesRow({ slug, colSpan }: { slug: string; colSpan: number }) {
  const queryClient = useQueryClient();
  const toast = useToast();

  const sources = useQuery({
    queryKey: ["sources", slug],
    queryFn: () => listSources(slug),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      return data.some((s) => s.run_status && ACTIVE_STATUSES.has(s.run_status)) ? 3000 : false;
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ sourceType, enabled }: { sourceType: string; enabled: boolean }) =>
      patchSource(slug, sourceType, { enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources", slug] }),
    onError: (err) => toast.err(extractErrorMessage(err)),
  });

  const ingestMutation = useMutation({
    mutationFn: (sourceType: string) => ingestSource(slug, sourceType),
    onSuccess: (data) =>
      toast.ok(`Enqueued ${data.enqueued_sources} source for ${data.plugin_slug}`),
    onError: (err) => toast.err(extractErrorMessage(err)),
  });

  const deleteMutation = useMutation({
    mutationFn: (sourceType: string) => deleteSource(slug, sourceType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources", slug] });
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      toast.ok("Source deleted");
    },
    onError: (err) => toast.err(extractErrorMessage(err)),
  });

  const addMutation = useMutation({
    mutationFn: (sourceType: string) => addSource(slug, sourceType),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["sources", slug] });
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      toast.ok(`Added source ${data.source_type}`);
    },
    onError: (err) => toast.err(extractErrorMessage(err)),
  });

  const usedTypes = new Set(sources.data?.map((s) => s.source_type) ?? []);

  return (
    <TableRow>
      <TableCell colSpan={colSpan} className="bg-muted/30 p-0">
        {sources.isLoading ? (
          <div className="flex flex-col gap-1.5 p-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : sources.isError ? (
          <div className="p-4">
            <ErrorState message={extractErrorMessage(sources.error)} />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/60 text-left text-[11px] font-medium text-muted-foreground">
                <th className="py-2 pl-4 pr-3 font-medium">Source type</th>
                <th className="py-2 pr-3 font-medium">Enabled</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">Last ingested</th>
                <th className="py-2 pr-3 font-medium">Chunks</th>
                <th className="py-2 pr-3 font-medium">Docs</th>
                <th className="py-2 pr-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sources.data!.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="py-3 pl-4 text-[12px] text-muted-foreground"
                  >
                    No sources. Add one below.
                  </td>
                </tr>
              ) : (
                sources.data!.map((s) => (
                  <SourceTableRow
                    key={s.source_id}
                    s={s}
                    onToggle={(sourceType, enabled) =>
                      toggleMutation.mutate({ sourceType, enabled })
                    }
                    onIngest={(sourceType) => ingestMutation.mutate(sourceType)}
                    onDelete={(sourceType) => deleteMutation.mutate(sourceType)}
                    toggleLoading={
                      toggleMutation.isPending &&
                      toggleMutation.variables?.sourceType === s.source_type
                    }
                    ingestLoading={
                      ingestMutation.isPending && ingestMutation.variables === s.source_type
                    }
                    deleteLoading={
                      deleteMutation.isPending && deleteMutation.variables === s.source_type
                    }
                  />
                ))
              )}
              <AddSourceRow
                usedTypes={usedTypes}
                onAdd={(sourceType) => addMutation.mutate(sourceType)}
                loading={addMutation.isPending}
              />
            </tbody>
          </table>
        )}
      </TableCell>
    </TableRow>
  );
}
