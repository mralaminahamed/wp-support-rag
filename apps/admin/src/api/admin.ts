// Admin + health API calls (app /api/v1/admin/*, /health). Author: Al Amin Ahamed.
import type {
  Health,
  EmbeddingConfigUpdate,
  IngestAllResponse,
  IngestTriggerResponse,
  LLMConfig,
  LLMConfigUpdate,
  Metrics,
  OllamaModels,
  PluginRegistration,
  PluginSummary,
  RecentQuery,
  SetupStatus,
  SourceSummary,
} from "@/types/api";

export type PatchSourcePayload = { enabled: boolean };
import { apiClient } from "./client";

export async function getHealth(): Promise<Health> {
  const res = await apiClient.get<Health>("/health", { validateStatus: () => true });
  return res.data;
}

export async function listPlugins(): Promise<PluginSummary[]> {
  const res = await apiClient.get<PluginSummary[]>("/api/v1/admin/plugins");
  return res.data;
}

export async function listSources(slug: string): Promise<SourceSummary[]> {
  const res = await apiClient.get<SourceSummary[]>(`/api/v1/admin/plugins/${slug}/sources`);
  return res.data;
}

export async function addSource(slug: string, sourceType: string): Promise<SourceSummary> {
  const res = await apiClient.post<SourceSummary>(`/api/v1/admin/plugins/${slug}/sources`, {
    source_type: sourceType,
  });
  return res.data;
}

export async function patchSource(
  slug: string,
  sourceType: string,
  payload: PatchSourcePayload,
): Promise<SourceSummary> {
  const res = await apiClient.patch<SourceSummary>(
    `/api/v1/admin/plugins/${slug}/sources/${sourceType}`,
    payload,
  );
  return res.data;
}

export async function deleteSource(slug: string, sourceType: string): Promise<void> {
  await apiClient.delete(`/api/v1/admin/plugins/${slug}/sources/${sourceType}`);
}

export async function ingestSource(slug: string, sourceType: string): Promise<IngestTriggerResponse> {
  const res = await apiClient.post<IngestTriggerResponse>(
    `/api/v1/admin/ingest/${slug}/${sourceType}`,
  );
  return res.data;
}

export async function registerPlugin(
  payload: PluginRegistration,
): Promise<{ slug: string; id: string }> {
  const res = await apiClient.post<{ slug: string; id: string }>(
    "/api/v1/admin/plugins",
    payload,
  );
  return res.data;
}

export async function ingestPlugin(slug: string): Promise<IngestTriggerResponse> {
  const res = await apiClient.post<IngestTriggerResponse>(`/api/v1/admin/ingest/${slug}`);
  return res.data;
}

export async function ingestAll(): Promise<IngestAllResponse> {
  const res = await apiClient.post<IngestAllResponse>("/api/v1/admin/ingest");
  return res.data;
}

export async function getMetrics(pluginSlug?: string): Promise<Metrics> {
  const res = await apiClient.get<Metrics>("/api/v1/admin/metrics", {
    params: pluginSlug ? { plugin_slug: pluginSlug } : undefined,
  });
  return res.data;
}

export async function getLlmConfig(): Promise<LLMConfig> {
  const res = await apiClient.get<LLMConfig>("/api/v1/admin/llm");
  return res.data;
}

export async function updateLlmConfig(payload: LLMConfigUpdate): Promise<LLMConfig> {
  const res = await apiClient.put<LLMConfig>("/api/v1/admin/llm", payload);
  return res.data;
}

export async function resetLlmConfig(): Promise<LLMConfig> {
  const res = await apiClient.delete<LLMConfig>("/api/v1/admin/llm");
  return res.data;
}

export async function updateEmbeddingConfig(payload: EmbeddingConfigUpdate): Promise<LLMConfig> {
  const res = await apiClient.put<LLMConfig>("/api/v1/admin/llm/embedding", payload);
  return res.data;
}

export async function resetEmbeddingConfig(): Promise<LLMConfig> {
  const res = await apiClient.delete<LLMConfig>("/api/v1/admin/llm/embedding");
  return res.data;
}

export async function getOllamaModels(): Promise<OllamaModels> {
  const res = await apiClient.get<OllamaModels>("/api/v1/admin/ollama/models");
  return res.data;
}

export async function getRecentQueries(limit = 8): Promise<RecentQuery[]> {
  const res = await apiClient.get<RecentQuery[]>("/api/v1/admin/queries", { params: { limit } });
  return res.data;
}

export async function getSetupStatus(): Promise<SetupStatus> {
  const res = await apiClient.get<SetupStatus>("/api/v1/admin/setup/status");
  return res.data;
}

export async function completeSetup(): Promise<SetupStatus> {
  const res = await apiClient.post<SetupStatus>("/api/v1/admin/setup/complete");
  return res.data;
}
