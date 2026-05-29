// Plugins: search, sort, expand sources, ingest per plugin / all. Author: Al Amin Ahamed.
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  GitBranch,
  Globe,
  Play,
  Plus,
  Search,
} from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { ingestAll, ingestPlugin, listPlugins } from "@/api/admin";
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
import { RegisterPluginModal } from "@/features/RegisterPluginModal";
import { SourcesRow } from "@/features/SourcesRow";
import { extractErrorMessage } from "@/lib/queryClient";

type SortKey = "slug" | "name" | "source_count";

export function PluginsPage() {
  const toast = useToast();
  const plugins = useQuery({ queryKey: ["plugins"], queryFn: listPlugins });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [registering, setRegistering] = useState(false);
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
              <Play /> Ingest all
            </Button>
            <Button onClick={() => setRegistering(true)}>
              <Plus /> Register plugin
            </Button>
          </>
        }
      />

      <div className="mb-3 flex items-center gap-3">
        <div className="relative max-w-xs flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
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
                        {open ? (
                          <ChevronDown className="size-4 text-muted-foreground" />
                        ) : (
                          <ChevronRight className="size-4 text-muted-foreground" />
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-[13px]">{p.slug}</TableCell>
                      <TableCell>{p.name}</TableCell>
                      <TableCell>
                        <Badge variant={p.status === "active" ? "success" : "secondary"}>
                          {p.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{p.source_count}</Badge>
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        {p.github_repo ? (
                          <RepoLink
                            href={`https://github.com/${p.github_repo}`}
                            title={p.github_repo}
                            icon={GitBranch}
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
                            icon={Globe}
                          />
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => ingestOne.mutate(p.slug)}
                          disabled={ingestOne.isPending}
                        >
                          Ingest
                        </Button>
                      </TableCell>
                    </TableRow>
                    {open && <SourcesRow slug={p.slug} colSpan={8} />}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Card>

      {registering && <RegisterPluginModal onClose={() => setRegistering(false)} />}
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

function RepoLink({
  href,
  title,
  icon: Icon,
}: {
  href: string;
  title: string;
  icon: typeof GitBranch;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={title}
      aria-label={title}
      className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition hover:bg-muted hover:text-primary"
    >
      <Icon className="size-4" />
    </a>
  );
}
