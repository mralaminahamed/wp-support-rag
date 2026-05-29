// Plugins: list, register, expand sources, ingest per plugin / all. Author: Al Amin Ahamed.
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Play, Plus } from "lucide-react";
import { Fragment, useState } from "react";
import { ingestAll, ingestPlugin, listPlugins } from "@/api/admin";
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
import { RegisterPluginModal } from "@/features/RegisterPluginModal";
import { SourcesRow } from "@/features/SourcesRow";
import { extractErrorMessage } from "@/lib/queryClient";

export function PluginsPage() {
  const toast = useToast();
  const plugins = useQuery({ queryKey: ["plugins"], queryFn: listPlugins });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [registering, setRegistering] = useState(false);

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

  return (
    <div>
      <PageHeader
        title="Plugins"
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
        ) : plugins.data!.length === 0 ? (
          <EmptyState title="No plugins yet" hint="Register one to start ingesting docs." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Slug</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Sources</TableHead>
                <TableHead>GitHub</TableHead>
                <TableHead>wp.org</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {plugins.data!.map((p) => (
                <Fragment key={p.slug}>
                  <TableRow>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => setExpanded(expanded === p.slug ? null : p.slug)}
                        aria-label="Toggle sources"
                      >
                        {expanded === p.slug ? <ChevronDown /> : <ChevronRight />}
                      </Button>
                    </TableCell>
                    <TableCell className="font-mono text-[13px]">{p.slug}</TableCell>
                    <TableCell>{p.name}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{p.source_count}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-[13px] text-muted-foreground">
                      {p.github_repo ?? "—"}
                    </TableCell>
                    <TableCell className="font-mono text-[13px] text-muted-foreground">
                      {p.wporg_slug ?? "—"}
                    </TableCell>
                    <TableCell className="text-right">
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
                  {expanded === p.slug && <SourcesRow slug={p.slug} colSpan={7} />}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {registering && <RegisterPluginModal onClose={() => setRegistering(false)} />}
    </div>
  );
}
