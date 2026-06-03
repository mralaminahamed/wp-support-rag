// Adapters management page: list adapter plugins, upload, delete. Author: Al Amin Ahamed.
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteAdapterPlugin, listAdapterPlugins, uploadAdapterPlugin } from "@/api/admin";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { extractErrorMessage } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import type { AdapterPluginSummary } from "@/types/api";

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_STYLE: Record<string, string> = {
  loaded:   "bg-success/10 text-success border-success/20",
  error:    "bg-destructive/10 text-destructive border-destructive/20",
  disabled: "bg-muted text-muted-foreground border-border",
};

function StatusBadge({ status, error }: { status: string; error: string | null }) {
  const cls = STATUS_STYLE[status] ?? "bg-muted text-muted-foreground border-border";
  return (
    <span
      title={status === "error" && error ? error : undefined}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium cursor-default",
        cls,
      )}
    >
      {status === "loaded" && <i className="ti ti-circle-check text-[10px]" />}
      {status === "error" && <i className="ti ti-alert-circle text-[10px]" />}
      {status === "disabled" && <i className="ti ti-minus text-[10px]" />}
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Source badge
// ---------------------------------------------------------------------------

const SOURCE_LABELS: Record<string, string> = {
  builtin:    "Built-in",
  entrypoint: "Package",
  file:       "File",
};

function SourceBadge({ source }: { source: string }) {
  return (
    <Badge variant="secondary" className="text-[10px] font-normal">
      {SOURCE_LABELS[source] ?? source}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Handles cell — join with comma, truncate at 3
// ---------------------------------------------------------------------------

function HandlesCell({ handles }: { handles: string[] }) {
  if (handles.length === 0) return <span className="text-muted-foreground text-[12px]">—</span>;
  const shown = handles.slice(0, 3).join(", ");
  const extra = handles.length - 3;
  return (
    <span className="text-[12px]" title={handles.join(", ")}>
      {shown}
      {extra > 0 && (
        <span className="text-muted-foreground ml-1">+{extra} more</span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Row component
// ---------------------------------------------------------------------------

function AdapterRow({
  adapter,
  onDelete,
  deleteLoading,
}: {
  adapter: AdapterPluginSummary;
  onDelete: (slug: string) => void;
  deleteLoading: boolean;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const canDelete = adapter.source === "file";

  return (
    <TableRow>
      <TableCell className="font-medium text-[13px]">
        <div className="flex flex-col gap-0.5">
          <span>{adapter.display_name}</span>
          <span className="font-mono text-[10px] text-muted-foreground">{adapter.slug}</span>
        </div>
      </TableCell>

      <TableCell>
        <HandlesCell handles={adapter.handles} />
      </TableCell>

      <TableCell>
        <SourceBadge source={adapter.source} />
      </TableCell>

      <TableCell className="text-[12px] text-muted-foreground">
        {adapter.version ?? <span className="text-muted-foreground/50">—</span>}
      </TableCell>

      <TableCell>
        <StatusBadge status={adapter.status} error={adapter.error} />
        {adapter.status === "error" && adapter.error && (
          <p
            className="max-w-[180px] truncate text-[10px] text-destructive mt-0.5"
            title={adapter.error}
          >
            {adapter.error}
          </p>
        )}
      </TableCell>

      <TableCell className="text-right">
        {canDelete ? (
          confirmDelete ? (
            <span className="inline-flex items-center gap-1.5 text-[11px]">
              <span className="text-destructive font-medium">Delete?</span>
              <button
                type="button"
                onClick={() => { onDelete(adapter.slug); setConfirmDelete(false); }}
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
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmDelete(true)}
              title="Delete this adapter"
              className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
            >
              <i className="ti ti-trash text-[12px]" />
            </Button>
          )
        ) : null}
      </TableCell>
    </TableRow>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function AdaptersPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const adapters = useQuery({ queryKey: ["adapter-plugins"], queryFn: listAdapterPlugins });

  const uploadMutation = useMutation({
    mutationFn: uploadAdapterPlugin,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["adapter-plugins"] });
      toast.ok("Adapter uploaded successfully.");
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAdapterPlugin,
    onSuccess: (_, slug) => {
      void qc.invalidateQueries({ queryKey: ["adapter-plugins"] });
      toast.ok(`Deleted adapter: ${slug}`);
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    uploadMutation.mutate(file);
    // reset so same file can be re-uploaded
    e.target.value = "";
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Adapters"
        description="Manage adapter plugins that handle source ingestion."
        actions={
          <>
            <Button
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadMutation.isPending}
            >
              {uploadMutation.isPending ? (
                <i className="ti ti-loader-2 animate-spin mr-1.5 text-[12px]" />
              ) : (
                <i className="ti ti-upload mr-1.5 text-[12px]" />
              )}
              Upload Adapter
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".py"
              className="hidden"
              onChange={handleFileChange}
            />
          </>
        }
      />

      {/* Info banner */}
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-4 py-2.5 text-[12px] text-muted-foreground">
        <i className="ti ti-info-circle text-[14px] shrink-0" />
        Container restart required to activate newly installed adapters.
      </div>

      <Card className="p-0 overflow-hidden">
        {adapters.isLoading ? (
          <div className="flex flex-col gap-2 p-4">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : adapters.isError ? (
          <div className="p-6">
            <ErrorState message={extractErrorMessage(adapters.error)} />
          </div>
        ) : adapters.data!.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No adapters"
              hint="Upload a .py adapter file to get started."
            />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Handles</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {adapters.data!.map((adapter) => (
                <AdapterRow
                  key={adapter.slug}
                  adapter={adapter}
                  onDelete={(slug) => deleteMutation.mutate(slug)}
                  deleteLoading={
                    deleteMutation.isPending && deleteMutation.variables === adapter.slug
                  }
                />
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}
