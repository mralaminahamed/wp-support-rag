// Plugins: search, sort, expand sources, ingest per plugin / all. Author: Al Amin Ahamed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { deletePlugin, ingestAll, ingestPlugin, listPlugins } from "@/api/admin";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
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
import { EditPluginModal } from "@/features/EditPluginModal";
import { RegisterPluginModal } from "@/features/RegisterPluginModal";
import { SourcesRow } from "@/features/SourcesRow";
import { extractErrorMessage } from "@/lib/queryClient";
import type { PluginSummary } from "@/types/api";

type SortKey = "slug" | "name" | "source_count" | "chunk_count";

export function PluginsPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const plugins = useQuery({ queryKey: ["plugins"], queryFn: listPlugins });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [registering, setRegistering] = useState(false);
  const [editing, setEditing] = useState<PluginSummary | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("slug");
  const [sortAsc, setSortAsc] = useState(true);

  const ingestOne = useMutation({
    mutationFn: ingestPlugin,
    onSuccess: (data) => toast.ok(`${data.plugin_slug}: enqueued ${data.enqueued_sources} sources`),
    onError: (error) => toast.err(extractErrorMessage(error)),
  });
  const ingestEvery = useMutation({
    mutationFn: ingestAll,
    onSuccess: (data) =>
      toast.ok(`Enqueued ${data.enqueued_sources} sources across ${data.plugins} plugins`),
    onError: (error) => toast.err(extractErrorMessage(error)),
  });
  const deleteMutation = useMutation({
    mutationFn: deletePlugin,
    onSuccess: (_, slug) => {
      toast.ok(`Deleted ${slug}`);
      void qc.invalidateQueries({ queryKey: ["plugins"] });
      setConfirmDelete(null);
      if (expanded === slug) setExpanded(null);
    },
    onError: (error) => toast.err(extractErrorMessage(error)),
  });

  function toggleSort(key: SortKey) {
    if (key === sortKey) setSortAsc((a) => !a);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  const rows = useMemo(() => {
    const all = plugins.data ?? [];
    const q = query.trim().toLowerCase();
    const filtered = q
      ? all.filter(
          (p) =>
            p.slug.toLowerCase().includes(q) ||
            p.name.toLowerCase().includes(q) ||
            (p.github_repo ?? "").toLowerCase().includes(q),
        )
      : all;
    const sorted = [...filtered].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
      return sortAsc ? cmp : -cmp;
    });
    return sorted;
  }, [plugins.data, query, sortKey, sortAsc]);

  const total = plugins.data?.length ?? 0;

  return (
    <div>
      <PageHeader
        title="Plugins"
        description="Registered plugins and their documentation sources."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => ingestEvery.mutate()}
              disabled={ingestEvery.isPending}
            >
              <i className="ti ti-player-play text-sm" /> Ingest all
            </Button>
            <Button onClick={() => setRegistering(true)}>
              <i className="ti ti-plus text-sm" /> Register plugin
            </Button>
          </>
        }
      />

      <div className="mb-3 flex items-center gap-3">
        <div className="relative max-w-xs flex-1">
          <i className="ti ti-search pointer-events-none absolute top-1/2 left-2.5 text-sm -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search slug, name, or repo…"
            className="pl-8"
          />
        </div>
        {!plugins.isLoading && (
          <span className="text-sm text-muted-foreground">
            {query ? `${rows.length} of ${total}` : `${total}`} plugins
          </span>
        )}
      </div>

      <Card className="py-0">
        {plugins.isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-9" />
            ))}
          </div>
        ) : plugins.isError ? (
          <div className="p-4">
            <ErrorState message={extractErrorMessage(plugins.error)} />
          </div>
        ) : total === 0 ? (
          <EmptyState title="No plugins yet" hint="Register one to start ingesting docs." />
        ) : rows.length === 0 ? (
          <EmptyState title="No matches" hint={`Nothing matches “${query}”.`} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <SortHeader label="Slug" col="slug" sortKey={sortKey} asc={sortAsc} onSort={toggleSort} />
                <SortHeader label="Name" col="name" sortKey={sortKey} asc={sortAsc} onSort={toggleSort} />
                <TableHead>Status</TableHead>
                <SortHeader
                  label="Sources"
                  col="source_count"
                  sortKey={sortKey}
                  asc={sortAsc}
                  onSort={toggleSort}
                />
                <SortHeader
                  label="Chunks"
                  col="chunk_count"
                  sortKey={sortKey}
                  asc={sortAsc}
                  onSort={toggleSort}
                />
                <TableHead>GitHub</TableHead>
                <TableHead>wp.org</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((p) => {
                const open = expanded === p.slug;
                return (
                  <Fragment key={p.slug}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={() => setExpanded(open ? null : p.slug)}
                    >
                      <TableCell>
                        <i className={`ti ${open ? "ti-chevron-down" : "ti-chevron-right"} text-sm text-muted-foreground`} />
                      </TableCell>
                      <TableCell className="font-mono text-[13px]">{p.slug}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <PluginIcon slug={p.slug} wporgSlug={p.wporg_slug} />
                          {p.name}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={p.status === "active" ? "success" : "secondary"}>
                          {p.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{p.source_count}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={p.chunk_count > 0 ? "accent" : "secondary"}>
                          {p.chunk_count.toLocaleString()}
                        </Badge>
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        {p.github_repo ? (
                          <RepoLink
                            href={`https://github.com/${p.github_repo}`}
                            title={p.github_repo}
                            icon="ti-brand-github"
                          />
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        {p.wporg_slug ? (
                          <RepoLink
                            href={`https://wordpress.org/plugins/${p.wporg_slug}/`}
                            title={p.wporg_slug}
                            icon="ti-world"
                          />
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1">
                          {confirmDelete === p.slug ? (
                            <>
                              <button
                                className="text-xs text-destructive hover:underline px-1"
                                onClick={() => deleteMutation.mutate(p.slug)}
                                disabled={deleteMutation.isPending}
                              >
                                Confirm
                              </button>
                              <button
                                className="text-xs text-muted-foreground hover:underline px-1"
                                onClick={() => setConfirmDelete(null)}
                              >
                                Cancel
                              </button>
                            </>
                          ) : (
                            <>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2"
                                onClick={() => setEditing(p)}
                              >
                                <i className="ti ti-pencil text-sm" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-destructive hover:text-destructive"
                                onClick={() => setConfirmDelete(p.slug)}
                              >
                                <i className="ti ti-trash text-sm" />
                              </Button>
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => ingestOne.mutate(p.slug)}
                                disabled={ingestOne.isPending}
                              >
                                Ingest
                              </Button>
                            </>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                    {open && <SourcesRow slug={p.slug} colSpan={9} />}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Card>

      {registering && <RegisterPluginModal onClose={() => setRegistering(false)} />}
      {editing && <EditPluginModal plugin={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function SortHeader({
  label,
  col,
  sortKey,
  asc,
  onSort,
}: {
  label: string;
  col: SortKey;
  sortKey: SortKey;
  asc: boolean;
  onSort: (col: SortKey) => void;
}) {
  const active = sortKey === col;
  return (
    <TableHead>
      <button
        type="button"
        onClick={() => onSort(col)}
        className="inline-flex items-center gap-1 font-medium transition hover:text-foreground"
      >
        {label}
        <span className={active ? "text-foreground" : "text-muted-foreground/40"}>
          {active ? (asc ? "↑" : "↓") : "↕"}
        </span>
      </button>
    </TableHead>
  );
}

const _PALETTE = ["#6366f1","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444","#ec4899"];
function _slugColor(slug: string): string {
  let h = 0;
  for (const c of slug) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
  return _PALETTE[h % _PALETTE.length]!;
}

function PluginIcon({ slug, wporgSlug }: { slug: string; wporgSlug: string | null }) {
  const [err, setErr] = useState(false);
  const letter = slug[0]?.toUpperCase() ?? "?";
  if (!wporgSlug || err) {
    return (
      <span
        className="inline-flex shrink-0 items-center justify-center rounded text-[11px] font-bold text-white"
        style={{ width: 28, height: 28, background: _slugColor(slug) }}
      >
        {letter}
      </span>
    );
  }
  return (
    <img
      src={`https://ps.w.org/${wporgSlug}/assets/icon-128x128.png`}
      width={28}
      height={28}
      alt={slug}
      className={cn("shrink-0 rounded object-cover")}
      onError={() => setErr(true)}
    />
  );
}

function RepoLink({ href, title, icon }: { href: string; title: string; icon: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={title}
      aria-label={title}
      className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition hover:bg-muted hover:text-primary"
    >
      <i className={`ti ${icon} text-sm`} />
    </a>
  );
}
