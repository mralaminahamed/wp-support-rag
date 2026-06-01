// API types mirroring apps/api schemas (app.api.schemas). Author: Al Amin Ahamed.

export const SOURCE_TYPES = [
  "github_readme",
  "github_changelog",
  "github_docs",
  "github_issues",
  "wporg_faq",
  "wporg_changelog",
  "wporg_support",
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
}

export interface SourceSummary {
  source_type: string;
  enabled: boolean;
  last_ingested_at: string | null;
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
  is_active: boolean;
  created_at: string;
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

