// Admin + health API calls (app /api/v1/admin/*, /health). Author: Al Amin Ahamed.
import type {
  AdapterPluginSummary,
  AdapterTypeInfo,
  AppendMessageItem,
  EmbeddingConfigUpdate,
  Health,
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
  ThreadMessage,
  ThreadSummary,
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

export async function addSource(
  slug: string,
  sourceType: string,
  name: string,
  config: Record<string, unknown> = {},
): Promise<SourceSummary> {
  const res = await apiClient.post<SourceSummary>(`/api/v1/admin/plugins/${slug}/sources`, {
    source_type: sourceType,
    name,
    config,
  });
  return res.data;
}

export async function patchSource(
  slug: string,
  sourceId: string,
  payload: PatchSourcePayload,
): Promise<SourceSummary> {
  const res = await apiClient.patch<SourceSummary>(
    `/api/v1/admin/plugins/${slug}/sources/${sourceId}`,
    payload,
  );
  return res.data;
}

export async function deleteSource(slug: string, sourceId: string): Promise<void> {
  await apiClient.delete(`/api/v1/admin/plugins/${slug}/sources/${sourceId}`);
}

export async function ingestSource(slug: string, sourceId: string): Promise<IngestTriggerResponse> {
  const res = await apiClient.post<IngestTriggerResponse>(
    `/api/v1/admin/ingest/${slug}/sources/${sourceId}`,
  );
  return res.data;
}

export async function patchSourceConfig(
  slug: string,
  sourceId: string,
  config: Record<string, unknown>,
): Promise<SourceSummary> {
  const res = await apiClient.patch<SourceSummary>(
    `/api/v1/admin/plugins/${slug}/sources/${sourceId}/config`,
    { config },
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

export async function updatePlugin(
  slug: string,
  payload: { name?: string; wporg_slug?: string | null; github_repo?: string | null; status?: "active" | "paused" },
): Promise<PluginSummary> {
  const res = await apiClient.patch<PluginSummary>(`/api/v1/admin/plugins/${slug}`, payload);
  return res.data;
}

export async function deletePlugin(slug: string): Promise<void> {
  await apiClient.delete(`/api/v1/admin/plugins/${slug}`);
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

export async function setupReset(): Promise<void> {
  await apiClient.post("/api/v1/admin/setup/reset");
}

export async function getSetupNetwork(): Promise<{ admin_url: string | null }> {
  const res = await apiClient.get<{ admin_url: string | null }>("/api/v1/admin/setup/network");
  return res.data;
}

export async function saveSetupNetwork(adminUrl: string): Promise<void> {
  await apiClient.put("/api/v1/admin/setup/network", { admin_url: adminUrl });
}

export async function setupCreateAdmin(
  email: string,
  password: string,
): Promise<{ id: string; email: string }> {
  const res = await apiClient.post<{ id: string; email: string }>(
    "/api/v1/admin/setup/create-admin",
    { email, password },
  );
  return res.data;
}

export async function getAdapterTypes(): Promise<AdapterTypeInfo[]> {
  const res = await apiClient.get<AdapterTypeInfo[]>("/api/v1/admin/adapter-plugins/types");
  return res.data;
}

export async function listAdapterPlugins(): Promise<AdapterPluginSummary[]> {
  const res = await apiClient.get<AdapterPluginSummary[]>("/api/v1/admin/adapter-plugins");
  return res.data;
}

export async function uploadAdapterPlugin(file: File): Promise<AdapterPluginSummary> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await apiClient.post<AdapterPluginSummary>(
    "/api/v1/admin/adapter-plugins/upload",
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return res.data;
}

export async function deleteAdapterPlugin(slug: string): Promise<void> {
  await apiClient.delete(`/api/v1/admin/adapter-plugins/${slug}`);
}

// ---------------------------------------------------------------------------
// Conversation threads
// ---------------------------------------------------------------------------

export async function listThreads(): Promise<ThreadSummary[]> {
  const res = await apiClient.get<ThreadSummary[]>("/api/v1/threads");
  return res.data;
}

export async function createThread(
  title: string,
  pluginSlug: string | null,
): Promise<ThreadSummary> {
  const res = await apiClient.post<ThreadSummary>("/api/v1/threads", {
    title,
    plugin_slug: pluginSlug || null,
  });
  return res.data;
}

export async function deleteThread(threadId: string): Promise<void> {
  await apiClient.delete(`/api/v1/threads/${threadId}`);
}

export async function getThreadMessages(threadId: string): Promise<ThreadMessage[]> {
  const res = await apiClient.get<ThreadMessage[]>(`/api/v1/threads/${threadId}/messages`);
  return res.data;
}

export async function appendMessages(
  threadId: string,
  messages: AppendMessageItem[],
): Promise<ThreadMessage[]> {
  const res = await apiClient.post<ThreadMessage[]>(`/api/v1/threads/${threadId}/messages`, {
    messages,
  });
  return res.data;
}
