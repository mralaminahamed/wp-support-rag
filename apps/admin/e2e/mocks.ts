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
  },
  {
    slug: "warranty-cart",
    name: "Warranty Cart",
    status: "active",
    wporg_slug: "warranty-cart",
    github_repo: null,
    source_count: 3,
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
};

const LLM_CONFIG = {
  provider: "anthropic",
  model: "claude-sonnet-4-6",
  source: "env",
  default_provider: "anthropic",
  providers: [
    { name: "anthropic", default_model: "claude-sonnet-4-6", configured: true },
    { name: "openai", default_model: "gpt-4o-mini", configured: true },
    { name: "ollama", default_model: "llama3.1", configured: true },
  ],
};

/** Register all API mocks. Specific routes are added last so they win. */
export async function mockApi(page: Page): Promise<void> {
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

  await page.route("**/api/v1/admin/plugins/*/sources", (route) =>
    route.fulfill({
      json: [
        { source_type: "wporg_faq", enabled: true, last_ingested_at: "2026-05-29T00:00:00Z" },
        { source_type: "github_readme", enabled: true, last_ingested_at: null },
      ],
    }),
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

  await page.route("**/api/v1/query", (route) => route.fulfill({ json: QUERY_RESPONSE }));
  await page.route("**/api/v1/feedback", (route) =>
    route.fulfill({ json: { status: "recorded" } }),
  );
}
