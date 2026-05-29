// Dashboard: KPIs, health, metrics, corpus overview, quick actions. Author: Al Amin Ahamed.
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Activity,
  Boxes,
  Database,
  DollarSign,
  Gauge,
  Layers,
  MessagesSquare,
  Play,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
  ThumbsUp,
  TriangleAlert,
  Zap,
} from "lucide-react";
import { Link } from "react-router-dom";
import { getHealth, getMetrics, ingestAll, listPlugins } from "@/api/admin";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import { pct } from "@/lib/format";
import { extractErrorMessage } from "@/lib/queryClient";

export function DashboardPage() {
  const toast = useToast();
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: () => getMetrics() });
  const plugins = useQuery({ queryKey: ["plugins"], queryFn: listPlugins });
  const ingestEvery = useMutation({
    mutationFn: ingestAll,
    onSuccess: (d) => toast.ok(`Enqueued ${d.enqueued_sources} sources across ${d.plugins} plugins`),
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const m = metrics.data;
  const totalSources = plugins.data?.reduce((sum, p) => sum + p.source_count, 0) ?? 0;
  const topPlugins = [...(plugins.data ?? [])]
    .sort((a, b) => b.source_count - a.source_count)
    .slice(0, 5);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Dashboard"
        description="Service health, query metrics, and corpus overview."
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              void health.refetch();
              void metrics.refetch();
              void plugins.refetch();
            }}
          >
            <RefreshCw /> Refresh
          </Button>
        }
      />

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {metrics.isLoading || !m ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[88px]" />)
        ) : (
          <>
            <StatCard icon={MessagesSquare} label="Total queries" value={m.total_queries} />
            <StatCard icon={ShieldCheck} label="Deflection" value={pct(m.deflection_rate)} tone="success" />
            <StatCard icon={ThumbsUp} label="Helpful" value={pct(m.helpful_rate)} />
            <StatCard icon={Gauge} label="p95 latency" value={`${m.p95_latency_ms} ms`} />
          </>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Left column */}
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Service health</CardTitle>
            </CardHeader>
            <CardContent>
              {health.isLoading ? (
                <Skeleton className="h-6 w-72" />
              ) : health.isError ? (
                <ErrorState message={extractErrorMessage(health.error)} />
              ) : (
                <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
                  <HealthItem icon={Activity} label="Status" value={health.data!.status} />
                  <HealthItem icon={Database} label="Database" value={health.data!.database} />
                  <HealthItem icon={Server} label="Redis" value={health.data!.redis} />
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">Environment</span>
                    <Badge variant="secondary">{health.data!.environment}</Badge>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Quality &amp; cost</CardTitle>
            </CardHeader>
            <CardContent>
              {metrics.isLoading || !m ? (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-[88px]" />
                  ))}
                </div>
              ) : metrics.isError ? (
                <ErrorState message={extractErrorMessage(metrics.error)} />
              ) : (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <StatCard icon={Zap} label="Cache hit" value={pct(m.cache_hit_rate)} />
                  <StatCard
                    icon={TriangleAlert}
                    label="Degraded"
                    value={pct(m.degraded_rate)}
                    tone={m.degraded_rate > 0 ? "warning" : "success"}
                  />
                  <StatCard icon={DollarSign} label="Mean / query" value={`$${m.mean_cost_usd.toFixed(4)}`} />
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right column */}
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Corpus</CardTitle>
            </CardHeader>
            <CardContent>
              {plugins.isLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : plugins.isError ? (
                <ErrorState message={extractErrorMessage(plugins.error)} />
              ) : (
                <>
                  <div className="mb-4 grid grid-cols-2 gap-3">
                    <StatCard icon={Boxes} label="Plugins" value={plugins.data!.length} />
                    <StatCard icon={Layers} label="Sources" value={totalSources} />
                  </div>
                  <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Top plugins
                  </p>
                  <ul className="space-y-1.5">
                    {topPlugins.map((p) => (
                      <li key={p.slug} className="flex items-center justify-between gap-2 text-sm">
                        <span className="truncate font-mono text-[13px]">{p.slug}</span>
                        <Badge variant="secondary">{p.source_count}</Badge>
                      </li>
                    ))}
                    {topPlugins.length === 0 && (
                      <li className="text-sm text-muted-foreground">No plugins registered.</li>
                    )}
                  </ul>
                  <Button asChild variant="ghost" size="sm" className="mt-3 w-full">
                    <Link to="/plugins">Manage plugins</Link>
                  </Button>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Quick actions</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2">
              <Button asChild variant="secondary" className="justify-start">
                <Link to="/playground">
                  <Sparkles /> Try a query
                </Link>
              </Button>
              <Button
                variant="secondary"
                className="justify-start"
                onClick={() => ingestEvery.mutate()}
                disabled={ingestEvery.isPending}
              >
                <Play /> Ingest all plugins
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function HealthItem({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
}) {
  const ok = value === "ok";
  return (
    <div className="flex items-center gap-2">
      <Icon className={ok ? "size-4 text-success" : "size-4 text-warning"} />
      <span className="text-xs text-muted-foreground">{label}</span>
      <Badge variant={ok ? "success" : "warning"}>{value}</Badge>
    </div>
  );
}
