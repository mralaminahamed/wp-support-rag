// Dashboard: health + aggregate metrics. Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { getHealth, getMetrics } from "@/api/admin";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { pct } from "@/lib/format";
import { extractErrorMessage } from "@/lib/queryClient";

export function DashboardPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: () => getMetrics() });

  return (
    <div>
      <PageHeader
        title="Dashboard"
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
        <CardContent className="flex flex-wrap gap-6">
          {health.isLoading ? (
            <Skeleton className="h-6 w-64" />
          ) : health.isError ? (
            <ErrorState message={extractErrorMessage(health.error)} />
          ) : (
            <>
              <HealthItem label="Status" value={health.data!.status} />
              <HealthItem label="Database" value={health.data!.database} />
              <HealthItem label="Redis" value={health.data!.redis} />
              <div>
                <p className="text-xs text-muted-foreground">Environment</p>
                <p className="mt-1 font-medium">{health.data!.environment}</p>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Metrics</CardTitle>
        </CardHeader>
        <CardContent>
          {metrics.isLoading ? (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : metrics.isError ? (
            <ErrorState message={extractErrorMessage(metrics.error)} />
          ) : (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <Stat label="Total queries" value={String(metrics.data!.total_queries)} />
              <Stat label="Deflection" value={pct(metrics.data!.deflection_rate)} />
              <Stat label="Helpful" value={pct(metrics.data!.helpful_rate)} />
              <Stat label="Cache hit" value={pct(metrics.data!.cache_hit_rate)} />
              <Stat label="Degraded" value={pct(metrics.data!.degraded_rate)} />
              <Stat label="Mean $/query" value={`$${metrics.data!.mean_cost_usd.toFixed(4)}`} />
              <Stat label="p95 latency" value={`${metrics.data!.p95_latency_ms} ms`} />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function HealthItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <Badge variant={value === "ok" ? "success" : "warning"} className="mt-1">
        {value}
      </Badge>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-muted/40 px-4 py-3">
      <p className="text-[13px] text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
    </div>
  );
}
