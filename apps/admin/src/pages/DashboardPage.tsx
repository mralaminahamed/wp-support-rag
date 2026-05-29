// Dashboard: health + aggregate metrics. Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { getHealth, getMetrics } from "@/api/admin";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHead } from "@/components/ui/card";
import { ErrorState, Skeleton } from "@/components/ui/feedback";
import { extractErrorMessage } from "@/lib/queryClient";
import { pct } from "@/lib/utils";

export function DashboardPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: () => getMetrics() });

  return (
    <div>
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-xl font-semibold">Dashboard</h2>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            void health.refetch();
            void metrics.refetch();
          }}
        >
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      <Card className="mb-5">
        <CardHead title="Service health" />
        <CardBody className="flex flex-wrap gap-6">
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
                <p className="text-xs text-muted">Environment</p>
                <p className="mt-1 font-medium">{health.data!.environment}</p>
              </div>
            </>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHead title="Metrics" />
        <CardBody>
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
        </CardBody>
      </Card>
    </div>
  );
}

function HealthItem({ label, value }: { label: string; value: string }) {
  const ok = value === "ok";
  return (
    <div>
      <p className="text-xs text-muted">{label}</p>
      <Badge tone={ok ? "ok" : "warn"} dot className="mt-1">
        {value}
      </Badge>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 px-4 py-3">
      <p className="text-[13px] text-muted">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
    </div>
  );
}
