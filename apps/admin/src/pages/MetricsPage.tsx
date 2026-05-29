// Metrics page: aggregate operational metrics from the admin API.
// Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import { getMetrics } from "@/api/admin";
import { extractErrorMessage } from "@/lib/queryClient";
import type { Metrics } from "@/types/api";

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function MetricsPage() {
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: () => getMetrics() });

  if (metrics.isLoading) return <p className="muted">Loading metrics…</p>;
  if (metrics.isError)
    return <p className="err">{extractErrorMessage(metrics.error)}</p>;

  const m = metrics.data as Metrics;
  const cards: Array<[string, string]> = [
    ["Queries", String(m.total_queries)],
    ["Deflection", pct(m.deflection_rate)],
    ["Helpful", pct(m.helpful_rate)],
    ["Cache hit", pct(m.cache_hit_rate)],
    ["Degraded", pct(m.degraded_rate)],
    ["Mean $/query", `$${m.mean_cost_usd.toFixed(4)}`],
    ["p95 latency", `${m.p95_latency_ms} ms`],
  ];

  return (
    <section>
      <button className="secondary" onClick={() => void metrics.refetch()}>
        Refresh
      </button>
      <div className="cards">
        {cards.map(([label, value]) => (
          <div className="card" key={label}>
            <span>{label}</span>
            <b>{value}</b>
          </div>
        ))}
      </div>
    </section>
  );
}
