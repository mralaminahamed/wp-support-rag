// API types mirroring apps/api schemas (app.api.schemas). Author: Al Amin Ahamed.

export const SOURCE_TYPES = [
  "github_readme",
  "github_changelog",
  "github_docs",
  "github_issues",
  "wporg_faq",
  "wporg_changelog",
  "wporg_support",
  "webpage",
  "rest_endpoint",
] as const;

export type SourceType = (typeof SOURCE_TYPES)[number];

export interface Health {
  status: string;
  service: string;
  environment: string;
  database: string;
  redis: string;
}

export interface PluginSummary {
  slug: string;
  name: string;
  status: string;
  wporg_slug: string | null;
  github_repo: string | null;
  source_count: number;
  chunk_count: number;
}

export interface SourceSummary {
  source_id: string;
  source_type: string;
  name: string;
  enabled: boolean;
  last_ingested_at: string | null;
  chunk_count: number;
  run_status: string | null;
  run_chunks: number | null;
  run_docs: number | null;
  run_error: string | null;
  run_finished_at: string | null;
}

export interface InviteSummary {
  id: string;
  email: string;
  role_name: string | null;
  status: "pending" | "expired" | "accepted";
  created_at: string;
  expires_at: string;
  used_at: string | null;
}

export interface PluginRegistration {
  slug: string;
  name: string;
  wporg_slug?: string | null;
  github_repo?: string | null;
  source_types: string[];
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

export interface SourceRef {
  url: string;
  heading_path: string | null;
  cited: boolean;
}

export interface LLMProviderInfo {
  name: string;
  default_model: string;
  configured: boolean;
}

export interface EmbeddingProviderInfo {
  name: string;
  default_model: string;
  dimensions: number;
  configured: boolean;
  applicable: boolean;
}

export interface EmbeddingConfig {
  provider: string;
  model: string;
  dimensions: number;
  source: "override" | "env";
  providers: EmbeddingProviderInfo[];
}

export interface LLMConfig {
  provider: string;
  model: string;
  source: "override" | "env";
  default_provider: string;
  providers: LLMProviderInfo[];
  embedding: EmbeddingConfig;
}

export interface LLMConfigUpdate {
  provider: string;
  model?: string | null;
}

export interface EmbeddingConfigUpdate {
  provider: string;
  model?: string | null;
}

export interface OllamaModels {
  reachable: boolean;
  base_url: string;
  models: string[];
}

export interface RecentQuery {
  id: string;
  query_text: string;
  plugin_slug: string | null;
  provider: string | null;
  cached: boolean;
  degraded: boolean;
  latency_ms: number | null;
  created_at: string;
  thread_id: string | null;
}

export interface QueryResponse {
  query_id: string;
  answer: string;
  citations: string[];
  sources: SourceRef[];
  cached: boolean;
  degraded: boolean;
  declined: boolean;
  plugin_slug: string | null;
  latency_ms: number;
  provider: string;
  model: string;
}

export interface AuthUser {
  id: string;
  email: string;
  roles: string[];
  permissions: string[];
  is_active: boolean;
  created_at: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface AcceptInviteRequest {
  token: string;
  password: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  password: string;
}

export interface UserListItem {
  id: string;
  email: string;
  roles: string[];
  permissions: string[];
  is_active: boolean;
  created_at: string;
  thread_count: number;
}

export interface CreateUserRequest {
  email: string;
  password: string;
  role_ids: string[];
}

export interface PatchUserRequest {
  is_active?: boolean;
  role_ids?: string[];
}

export interface InviteRequest {
  email: string;
  role_id: string;
}

export interface InviteResponse {
  token: string;
  invite_url: string | null;
}

export interface RoleSummary {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  permissions: string[];
}

export interface CreateRoleRequest {
  name: string;
  description?: string | null;
  permissions: string[];
}

export interface PatchRoleRequest {
  description?: string | null;
  permissions?: string[];
}

export interface SetupStatus {
  complete: boolean;
}

export interface ThreadSummary {
  id: string;
  title: string;
  plugin_slug: string | null;
  created_at: string;
  updated_at: string;
  owner_email?: string | null;
}

export interface ThreadMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  query_id: string | null;
  meta: Record<string, unknown> | null;
  created_at: string;
}

export interface AppendMessageItem {
  role: "user" | "assistant";
  content: string;
  query_id?: string | null;
  meta?: Record<string, unknown> | null;
}

export interface TicketSummary {
  id: string;
  title: string;
  source_url: string;
  plugin_slug: string;
  fetched_at: string;
  chunk_count: number;
  creator: string | null;
  reply_count: number | null;
  participant_count: number | null;
  last_reply_at: string | null;
}

export interface TicketReply {
  id: number;
  author: string;
  author_url: string | null;
  content: string;
  created_at: string;
  is_topic: boolean;
}

export interface TicketDetail {
  id: string;
  title: string;
  source_url: string;
  plugin_slug: string;
  replies: TicketReply[];
  wporg_topic_id: number | null;
  error: string | null;
}

export interface PostReplyRequest {
  content: string;
}

export interface PostReplyResponse {
  success: boolean;
  message: string;
  reply_url: string | null;
}

export interface WporgCredentials {
  configured: boolean;
  username: string | null;
}

export interface AdapterTypeInfo {
  source_type: string;
  display_name: string;
  adapter_slug: string;
  config_schema: Record<string, unknown>;
  is_builtin: boolean;
  multi_instance: boolean;
}

export interface AdapterPluginSummary {
  slug: string;
  display_name: string;
  version: string | null;
  source: "builtin" | "entrypoint" | "file";
  handles: string[];
  status: "loaded" | "error" | "disabled";
  error: string | null;
  installed_at: string;
}

