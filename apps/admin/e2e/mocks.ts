// Mock the admin/query API via page.route so e2e needs no backend.
// Author: Al Amin Ahamed.
import type { Page } from "@playwright/test";

export const PLUGINS = [
  {
    slug: "swift-menu-duplicator",
    name: "Swift Menu Duplicator",
    status: "active",
    wporg_slug: "swift-menu-duplicator",
    github_repo: "mralaminahamed/swift-menu-duplicator",
    source_count: 7,
    chunk_count: 420,
  },
  {
    slug: "warranty-cart",
    name: "Warranty Cart",
    status: "active",
    wporg_slug: "warranty-cart",
    github_repo: null,
    source_count: 3,
    chunk_count: 0,
  },
];

const METRICS = {
  total_queries: 128,
  deflection_rate: 0.91,
  helpful_rate: 0.84,
  cache_hit_rate: 0.42,
  degraded_rate: 0.05,
  mean_cost_usd: 0.0123,
  p95_latency_ms: 870,
};

const QUERY_RESPONSE = {
  query_id: "11111111-1111-1111-1111-111111111111",
  answer: "Theme location assignments are not copied because they are site-specific.",
  citations: ["https://wordpress.org/plugins/swift-menu-duplicator/#faq"],
  sources: [
    {
      url: "https://wordpress.org/plugins/swift-menu-duplicator/#faq",
      heading_path: "FAQ",
      cited: true,
    },
  ],
  cached: false,
  degraded: false,
  declined: false,
  plugin_slug: "swift-menu-duplicator",
  latency_ms: 540,
  provider: "ollama",
  model: "llama3.2",
};

const EMBEDDING_CONFIG = {
  provider: "openai",
  model: "text-embedding-3-large",
  dimensions: 3072,
  source: "env",
  providers: [
    {
      name: "openai",
      default_model: "text-embedding-3-large",
      dimensions: 3072,
      configured: true,
      applicable: true,
    },
    {
      name: "ollama",
      default_model: "nomic-embed-text",
      dimensions: 768,
      configured: true,
      applicable: false,
    },
  ],
};

const LLM_CONFIG = {
  provider: "anthropic",
  model: "claude-sonnet-4-6",
  source: "env",
  default_provider: "anthropic",
  providers: [
    { name: "anthropic", default_model: "claude-sonnet-4-6", configured: true },
    { name: "openai", default_model: "gpt-4o-mini", configured: true },
    { name: "ollama", default_model: "llama3.2", configured: true },
  ],
  embedding: EMBEDDING_CONFIG,
};

const MOCK_USER = {
  id: "00000000-0000-0000-0000-000000000001",
  email: "admin@example.com",
  roles: ["admin"],
  permissions: [
    "plugins:read", "plugins:write",
    "ingestion:trigger",
    "metrics:read",
    "settings:read", "settings:write",
    "users:read", "users:write",
  ],
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

/** Register all API mocks. Specific routes are added last so they win. */
export async function mockApi(page: Page): Promise<void> {
  // Auth — must resolve before RequireAuth renders any protected page
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: MOCK_USER }));
  await page.route("**/api/v1/admin/setup/status", (route) =>
    route.fulfill({ json: { complete: true } }),
  );
  await page.route("**/api/v1/admin/setup/network", (route) =>
    route.fulfill({ json: { admin_url: null } }),
  );
  await page.route("**/api/v1/admin/setup/reset", (route) =>
    route.fulfill({ json: { wiped: true } }),
  );
  await page.route("**/api/v1/admin/setup/create-admin", (route) =>
    route.fulfill({ status: 201, json: { id: "u1", email: "admin@example.com" } }),
  );

  await page.route("**/health", (route) =>
    route.fulfill({
      json: {
        status: "ok",
        service: "wp-support-rag",
        environment: "development",
        database: "ok",
        redis: "ok",
      },
    }),
  );

  await page.route("**/api/v1/admin/metrics**", (route) => route.fulfill({ json: METRICS }));

  await page.route("**/api/v1/admin/queries**", (route) =>
    route.fulfill({
      json: [
        {
          id: "q1",
          query_text: "How do I duplicate a menu?",
          plugin_slug: "swift-menu-duplicator",
          provider: "ollama",
          cached: false,
          degraded: false,
          latency_ms: 540,
          created_at: "2026-05-29T07:00:00Z",
        },
      ],
    }),
  );

  await page.route("**/api/v1/admin/plugins/*/sources/*", (route) => {
    const method = route.request().method();
    if (method === "PATCH") {
      const body = route.request().postDataJSON() as { enabled: boolean };
      route.fulfill({
        json: {
          source_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
          source_type: "wporg_faq",
          enabled: body.enabled,
          last_ingested_at: "2026-05-29T00:00:00Z",
        },
      });
    } else if (method === "DELETE") {
      route.fulfill({ status: 204, body: "" });
    } else {
      route.fulfill({ status: 404, json: { detail: "not found" } });
    }
  });

  await page.route("**/api/v1/admin/plugins/*/sources", (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as { source_type: string };
      route.fulfill({
        status: 201,
        json: {
          source_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
          source_type: body.source_type,
          enabled: true,
          last_ingested_at: null,
        },
      });
    } else {
      route.fulfill({
        json: [
          {
            source_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            source_type: "wporg_faq",
            enabled: true,
            last_ingested_at: "2026-05-29T00:00:00Z",
            run_status: "succeeded",
            run_chunks: 120,
            run_docs: 14,
            run_error: null,
            run_finished_at: "2026-05-29T01:00:00Z",
          },
          {
            source_id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
            source_type: "github_readme",
            enabled: true,
            last_ingested_at: null,
            run_status: null,
            run_chunks: null,
            run_docs: null,
            run_error: null,
            run_finished_at: null,
          },
        ],
      });
    }
  });

  // Single-source ingest (more specific — registered first so it wins)
  await page.route("**/api/v1/admin/ingest/*/*", (route) =>
    route.fulfill({ json: { plugin_slug: "swift-menu-duplicator", enqueued_sources: 1 } }),
  );

  await page.route("**/api/v1/admin/ingest/*", (route) =>
    route.fulfill({ json: { plugin_slug: "swift-menu-duplicator", enqueued_sources: 7 } }),
  );

  await page.route("**/api/v1/admin/ingest", (route) =>
    route.fulfill({ json: { plugins: 2, enqueued_sources: 10, by_plugin: [] } }),
  );

  await page.route("**/api/v1/admin/plugins", (route) => {
    if (route.request().method() === "POST") {
      route.fulfill({ json: { slug: "new-plugin", id: "abc" } });
    } else {
      route.fulfill({ json: PLUGINS });
    }
  });

  await page.route("**/api/v1/admin/llm", (route) => {
    const method = route.request().method();
    if (method === "PUT") {
      const body = route.request().postDataJSON() as { provider: string; model?: string };
      const fallback = LLM_CONFIG.providers.find((p) => p.name === body.provider)?.default_model;
      route.fulfill({
        json: {
          ...LLM_CONFIG,
          provider: body.provider,
          model: body.model || fallback || LLM_CONFIG.model,
          source: "override",
        },
      });
    } else if (method === "DELETE") {
      route.fulfill({ json: LLM_CONFIG });
    } else {
      route.fulfill({ json: LLM_CONFIG });
    }
  });

  await page.route("**/api/v1/admin/ollama/models", (route) =>
    route.fulfill({
      json: {
        reachable: true,
        base_url: "http://host.docker.internal:11434",
        models: ["llama3.2", "nomic-embed-text", "qwen3-embedding:4b"],
      },
    }),
  );

  await page.route("**/api/v1/admin/llm/embedding", (route) => {
    const method = route.request().method();
    if (method === "PUT") {
      const body = route.request().postDataJSON() as { provider: string; model?: string };
      const info = EMBEDDING_CONFIG.providers.find((p) => p.name === body.provider);
      if (info && !info.applicable) {
        route.fulfill({ status: 409, json: { detail: "needs migration + re-ingest" } });
        return;
      }
      route.fulfill({
        json: {
          ...LLM_CONFIG,
          embedding: {
            ...EMBEDDING_CONFIG,
            provider: body.provider,
            model: body.model || info?.default_model || EMBEDDING_CONFIG.model,
            source: "override",
          },
        },
      });
    } else if (method === "DELETE") {
      route.fulfill({ json: LLM_CONFIG });
    } else {
      route.fulfill({ json: LLM_CONFIG });
    }
  });

  await page.route("**/api/v1/query", (route) => route.fulfill({ json: QUERY_RESPONSE }));
  await page.route("**/api/v1/feedback", (route) =>
    route.fulfill({ json: { status: "recorded" } }),
  );

  // Conversation threads — register broad → specific (LIFO: last wins)
  await page.route("**/api/v1/threads", (route) => {
    if (route.request().method() === "POST") {
      route.fulfill({ status: 201, json: { id: "t1", title: "Test thread", plugin_slug: null, created_at: "2026-06-02T00:00:00Z", updated_at: "2026-06-02T00:00:00Z" } });
    } else {
      route.fulfill({ json: [] });
    }
  });
  await page.route("**/api/v1/threads/*", (route) => {
    if (route.request().method() === "DELETE") {
      route.fulfill({ status: 204, body: "" });
    } else {
      route.fulfill({ json: { id: "t1", title: "Test thread", plugin_slug: null, created_at: "2026-06-02T00:00:00Z", updated_at: "2026-06-02T00:00:00Z" } });
    }
  });
  await page.route("**/api/v1/threads/*/messages", (route) => {
    if (route.request().method() === "POST") {
      route.fulfill({ status: 201, json: [] });
    } else {
      route.fulfill({ json: [] });
    }
  });
}
