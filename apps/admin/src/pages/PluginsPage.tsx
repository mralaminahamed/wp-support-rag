// Plugins: list, register, expand sources, ingest per plugin / all. Author: Al Amin Ahamed.
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Play, Plus } from "lucide-react";
import { Fragment, useState } from "react";
import { ingestAll, ingestPlugin, listPlugins } from "@/api/admin";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
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
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-xl font-semibold">Plugins</h2>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            onClick={() => ingestEvery.mutate()}
            disabled={ingestEvery.isPending}
          >
            <Play className="h-4 w-4" /> Ingest all
          </Button>
          <Button onClick={() => setRegistering(true)}>
            <Plus className="h-4 w-4" /> Register plugin
          </Button>
        </div>
      </div>

      <Card>
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
          <table>
            <thead>
              <tr>
                <th className="w-8" />
                <th>Slug</th>
                <th>Name</th>
                <th>Sources</th>
                <th>GitHub</th>
                <th>wp.org</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {plugins.data!.map((p) => (
                <Fragment key={p.slug}>
                  <tr className="hover:bg-surface-2">
                    <td>
                      <button
                        className="text-muted hover:text-fg"
                        onClick={() => setExpanded(expanded === p.slug ? null : p.slug)}
                        aria-label="Toggle sources"
                      >
                        {expanded === p.slug ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </button>
                    </td>
                    <td className="font-mono text-[13px]">{p.slug}</td>
                    <td>{p.name}</td>
                    <td>
                      <Badge tone="neutral">{p.source_count}</Badge>
                    </td>
                    <td className="font-mono text-[13px] text-muted">{p.github_repo ?? "—"}</td>
                    <td className="font-mono text-[13px] text-muted">{p.wporg_slug ?? "—"}</td>
                    <td className="text-right">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => ingestOne.mutate(p.slug)}
                        disabled={ingestOne.isPending}
                      >
                        Ingest
                      </Button>
                    </td>
                  </tr>
                  {expanded === p.slug && <SourcesRow slug={p.slug} colSpan={7} />}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {registering && <RegisterPluginModal onClose={() => setRegistering(false)} />}
    </div>
  );
}
