// Dashboard: health + aggregate metrics. Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Database,
  DollarSign,
  Gauge,
  MessagesSquare,
  RefreshCw,
  Server,
  ShieldCheck,
  ThumbsUp,
  TriangleAlert,
  Zap,
} from "lucide-react";
import { getHealth, getMetrics } from "@/api/admin";
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
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: () => getMetrics() });

  const m = metrics.data;
  const tone = (degraded: number) => (degraded > 0 ? "warning" : "success");

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Service health and aggregate query metrics."
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              void health.refetch();
              void metrics.refetch();
            }}
          >
            <RefreshCw /> Refresh
          </Button>
        }
      />

      <Card className="mb-5">
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
          <CardTitle>Metrics</CardTitle>
        </CardHeader>
        <CardContent>
          {metrics.isLoading ? (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {Array.from({ length: 7 }).map((_, i) => (
                <Skeleton key={i} className="h-[88px]" />
              ))}
            </div>
          ) : metrics.isError ? (
            <ErrorState message={extractErrorMessage(metrics.error)} />
          ) : (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatCard icon={MessagesSquare} label="Total queries" value={m!.total_queries} />
              <StatCard
                icon={ShieldCheck}
                label="Deflection"
                value={pct(m!.deflection_rate)}
                tone="success"
              />
              <StatCard icon={ThumbsUp} label="Helpful" value={pct(m!.helpful_rate)} />
              <StatCard icon={Zap} label="Cache hit" value={pct(m!.cache_hit_rate)} />
              <StatCard
                icon={TriangleAlert}
                label="Degraded"
                value={pct(m!.degraded_rate)}
                tone={tone(m!.degraded_rate)}
              />
              <StatCard icon={DollarSign} label="Mean / query" value={`$${m!.mean_cost_usd.toFixed(4)}`} />
              <StatCard icon={Gauge} label="p95 latency" value={`${m!.p95_latency_ms} ms`} />
            </div>
          )}
        </CardContent>
      </Card>
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
