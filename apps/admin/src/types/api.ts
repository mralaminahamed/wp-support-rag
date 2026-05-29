// API response types mirroring apps/api schemas (apps.api.api.schemas).
// Author: Al Amin Ahamed.

export interface PluginSummary {
  slug: string;
  name: string;
  status: string;
  wporg_slug: string | null;
  github_repo: string | null;
  source_count: number;
}

export interface SourceSummary {
  source_type: string;
  enabled: boolean;
  last_ingested_at: string | null;
}

export interface IngestTriggerResponse {
  plugin_slug: string;
  enqueued_sources: number;
}

export interface IngestAllResponse {
  plugins: number;
  enqueued_sources: number;
  by_plugin: IngestTriggerResponse[];
}

export interface Metrics {
  total_queries: number;
  deflection_rate: number;
  helpful_rate: number;
  cache_hit_rate: number;
  degraded_rate: number;
  mean_cost_usd: number;
  p95_latency_ms: number;
}
