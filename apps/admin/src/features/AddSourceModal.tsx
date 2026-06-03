// Two-step add-source modal: type picker → config form. Author: Al Amin Ahamed.
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { addSource } from "@/api/admin";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ToastProvider";
import { extractErrorMessage } from "@/lib/queryClient";
import { SOURCE_TYPES } from "@/types/api";

const MULTI_INSTANCE_TYPES = new Set(["webpage", "rest_endpoint"]);

const TYPE_ICONS: Record<string, string> = {
  github_readme: "ti-brand-github",
  github_changelog: "ti-file-text",
  github_docs: "ti-book",
  github_issues: "ti-message-circle",
  wporg_faq: "ti-help-circle",
  wporg_changelog: "ti-clock",
  wporg_support: "ti-messages",
  webpage: "ti-world",
  rest_endpoint: "ti-api",
};

interface WebpageConfig {
  url: string;
  name: string;
  max_depth: number;
  selector: string;
  url_filter: string;
}

interface RestConfig {
  url: string;
  name: string;
  method: "GET" | "POST";
  auth_type: "none" | "bearer" | "api_key";
  bearer_token: string;
  api_key_header: string;
  api_key_value: string;
  content_field: string;
  title_field: string;
  url_field: string;
  id_field: string;
  pagination: "none" | "page_param" | "link_header" | "cursor";
  page_param: string;
  page_size_param: string;
  page_size: number;
  cursor_field: string;
  items_path: string;
}

function buildHeaders(cfg: RestConfig): Record<string, string> {
  if (cfg.auth_type === "bearer") return { Authorization: `Bearer ${cfg.bearer_token}` };
  if (cfg.auth_type === "api_key") return { [cfg.api_key_header]: cfg.api_key_value };
  return {};
}

function buildRestConfig(cfg: RestConfig): Record<string, unknown> {
  const out: Record<string, unknown> = {
    url: cfg.url,
    method: cfg.method,
    content_field: cfg.content_field,
    id_field: cfg.id_field,
    pagination: cfg.pagination,
  };
  const headers = buildHeaders(cfg);
  if (Object.keys(headers).length) out.headers = headers;
  if (cfg.title_field) out.title_field = cfg.title_field;
  if (cfg.url_field) out.url_field = cfg.url_field;
  if (cfg.items_path) out.items_path = cfg.items_path;
  if (cfg.pagination === "page_param") {
    out.page_param = cfg.page_param;
    out.page_size_param = cfg.page_size_param;
    out.page_size = cfg.page_size;
  }
  if (cfg.pagination === "cursor") out.cursor_field = cfg.cursor_field;
  return out;
}

function WebpageConfigForm({
  cfg,
  setCfg,
}: {
  cfg: WebpageConfig;
  setCfg: (c: WebpageConfig) => void;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium mb-1">Name <span className="text-destructive">*</span></label>
        <input
          className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="e.g. Plugin Docs Site"
          value={cfg.name}
          onChange={(e) => setCfg({ ...cfg, name: e.target.value })}
        />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Start URL <span className="text-destructive">*</span></label>
        <input
          type="url"
          className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="https://docs.example.com/"
          value={cfg.url}
          onChange={(e) => {
            const url = e.target.value;
            const hostname = (() => { try { return new URL(url).hostname; } catch { return ""; } })();
            setCfg({ ...cfg, url, name: cfg.name || hostname });
          }}
        />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Max depth (1–5)</label>
        <div className="flex items-center gap-3">
          <input
            type="range" min={1} max={5} value={cfg.max_depth}
            onChange={(e) => setCfg({ ...cfg, max_depth: Number(e.target.value) })}
            className="flex-1"
          />
          <span className="text-sm font-mono w-4">{cfg.max_depth}</span>
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">CSS selector <span className="text-muted-foreground">(optional)</span></label>
        <input
          className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="main, article, [role=main], body"
          value={cfg.selector}
          onChange={(e) => setCfg({ ...cfg, selector: e.target.value })}
        />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">URL filter regex <span className="text-muted-foreground">(optional — defaults to same domain)</span></label>
        <input
          className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="^https://docs\.example\.com/"
          value={cfg.url_filter}
          onChange={(e) => setCfg({ ...cfg, url_filter: e.target.value })}
        />
      </div>
    </div>
  );
}

function RestConfigForm({ cfg, setCfg }: { cfg: RestConfig; setCfg: (c: RestConfig) => void }) {
  return (
    <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
      <div>
        <label className="block text-xs font-medium mb-1">Name <span className="text-destructive">*</span></label>
        <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="e.g. Plugin REST API" value={cfg.name}
          onChange={(e) => setCfg({ ...cfg, name: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Endpoint URL <span className="text-destructive">*</span></label>
        <input type="url" className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="https://api.example.com/v1/posts" value={cfg.url}
          onChange={(e) => setCfg({ ...cfg, url: e.target.value })} />
      </div>
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="block text-xs font-medium mb-1">Method</label>
          <select className="w-full rounded border border-border bg-background px-2 py-1.5 text-sm focus:outline-none"
            value={cfg.method} onChange={(e) => setCfg({ ...cfg, method: e.target.value as "GET" | "POST" })}>
            <option value="GET">GET</option>
            <option value="POST">POST</option>
          </select>
        </div>
        <div className="flex-1">
          <label className="block text-xs font-medium mb-1">Auth</label>
          <select className="w-full rounded border border-border bg-background px-2 py-1.5 text-sm focus:outline-none"
            value={cfg.auth_type} onChange={(e) => setCfg({ ...cfg, auth_type: e.target.value as RestConfig["auth_type"] })}>
            <option value="none">None</option>
            <option value="bearer">Bearer token</option>
            <option value="api_key">API key header</option>
          </select>
        </div>
      </div>
      {cfg.auth_type === "bearer" && (
        <div>
          <label className="block text-xs font-medium mb-1">Bearer token</label>
          <input type="password" className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={cfg.bearer_token} onChange={(e) => setCfg({ ...cfg, bearer_token: e.target.value })} />
        </div>
      )}
      {cfg.auth_type === "api_key" && (
        <div className="flex gap-2">
          <input className="flex-1 rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none"
            placeholder="Header name (e.g. X-API-Key)" value={cfg.api_key_header}
            onChange={(e) => setCfg({ ...cfg, api_key_header: e.target.value })} />
          <input type="password" className="flex-1 rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none"
            placeholder="Value" value={cfg.api_key_value}
            onChange={(e) => setCfg({ ...cfg, api_key_value: e.target.value })} />
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium mb-1">Content field <span className="text-destructive">*</span></label>
          <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
            placeholder="body" value={cfg.content_field}
            onChange={(e) => setCfg({ ...cfg, content_field: e.target.value })} />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">ID field <span className="text-destructive">*</span></label>
          <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
            placeholder="id" value={cfg.id_field}
            onChange={(e) => setCfg({ ...cfg, id_field: e.target.value })} />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">Title field</label>
          <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
            placeholder="title" value={cfg.title_field}
            onChange={(e) => setCfg({ ...cfg, title_field: e.target.value })} />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">URL field</label>
          <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
            placeholder="url" value={cfg.url_field}
            onChange={(e) => setCfg({ ...cfg, url_field: e.target.value })} />
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Items path <span className="text-muted-foreground">(dot-separated, e.g. data.results)</span></label>
        <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
          placeholder="data" value={cfg.items_path}
          onChange={(e) => setCfg({ ...cfg, items_path: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Pagination</label>
        <select className="w-full rounded border border-border bg-background px-2 py-1.5 text-sm focus:outline-none"
          value={cfg.pagination} onChange={(e) => setCfg({ ...cfg, pagination: e.target.value as RestConfig["pagination"] })}>
          <option value="none">None (single request)</option>
          <option value="page_param">Page number param</option>
          <option value="link_header">Link header (RFC 5988)</option>
          <option value="cursor">Cursor field</option>
        </select>
      </div>
      {cfg.pagination === "page_param" && (
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="block text-xs font-medium mb-1">Page param</label>
            <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
              value={cfg.page_param} onChange={(e) => setCfg({ ...cfg, page_param: e.target.value })} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Size param</label>
            <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
              value={cfg.page_size_param} onChange={(e) => setCfg({ ...cfg, page_size_param: e.target.value })} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Page size</label>
            <input type="number" className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none"
              value={cfg.page_size} onChange={(e) => setCfg({ ...cfg, page_size: Number(e.target.value) })} />
          </div>
        </div>
      )}
      {cfg.pagination === "cursor" && (
        <div>
          <label className="block text-xs font-medium mb-1">Cursor field (dot-path in response)</label>
          <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
            placeholder="next_cursor" value={cfg.cursor_field}
            onChange={(e) => setCfg({ ...cfg, cursor_field: e.target.value })} />
        </div>
      )}
    </div>
  );
}

const DEFAULT_WEBPAGE: WebpageConfig = { url: "", name: "", max_depth: 2, selector: "", url_filter: "" };
const DEFAULT_REST: RestConfig = {
  url: "", name: "", method: "GET", auth_type: "none",
  bearer_token: "", api_key_header: "", api_key_value: "",
  content_field: "", title_field: "", url_field: "", id_field: "",
  pagination: "none", page_param: "page", page_size_param: "per_page",
  page_size: 100, cursor_field: "", items_path: "",
};

export function AddSourceModal({
  slug,
  usedTypes,
  onClose,
}: {
  slug: string;
  usedTypes: Set<string>;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [step, setStep] = useState<"pick" | "configure">("pick");
  const [selectedType, setSelectedType] = useState<string>("");
  const [webCfg, setWebCfg] = useState<WebpageConfig>(DEFAULT_WEBPAGE);
  const [restCfg, setRestCfg] = useState<RestConfig>(DEFAULT_REST);

  const mutation = useMutation({
    mutationFn: ({ type, name, config }: { type: string; name: string; config: Record<string, unknown> }) =>
      addSource(slug, type, name, config),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["sources", slug] });
      qc.invalidateQueries({ queryKey: ["plugins"] });
      toast.ok(`Added source "${data.name}"`);
      onClose();
    },
    onError: (err) => toast.err(extractErrorMessage(err)),
  });

  const singleTypes = SOURCE_TYPES.filter((t) => !MULTI_INSTANCE_TYPES.has(t) && !usedTypes.has(t));
  const multiTypes = SOURCE_TYPES.filter((t) => MULTI_INSTANCE_TYPES.has(t));

  function handlePickType(type: string) {
    if (MULTI_INSTANCE_TYPES.has(type)) {
      setSelectedType(type);
      setStep("configure");
    } else {
      mutation.mutate({ type, name: type, config: {} });
    }
  }

  function handleSubmitConfig() {
    if (selectedType === "webpage") {
      mutation.mutate({
        type: "webpage",
        name: webCfg.name,
        config: {
          url: webCfg.url,
          max_depth: webCfg.max_depth,
          ...(webCfg.selector ? { selector: webCfg.selector } : {}),
          ...(webCfg.url_filter ? { url_filter: webCfg.url_filter } : {}),
        },
      });
    } else {
      mutation.mutate({
        type: "rest_endpoint",
        name: restCfg.name,
        config: buildRestConfig(restCfg),
      });
    }
  }

  const configValid = selectedType === "webpage"
    ? webCfg.url.trim() !== "" && webCfg.name.trim() !== ""
    : restCfg.url.trim() !== "" && restCfg.name.trim() !== "" &&
      restCfg.content_field.trim() !== "" && restCfg.id_field.trim() !== "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-background border border-border rounded-xl shadow-xl w-full max-w-lg mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-base font-semibold">
            {step === "pick" ? "Add source" : `Configure ${selectedType.replace("_", " ")}`}
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <i className="ti ti-x text-sm" />
          </button>
        </div>

        <div className="p-5">
          {step === "pick" ? (
            <div className="space-y-4">
              {singleTypes.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">GitHub &amp; WordPress.org</p>
                  <div className="grid grid-cols-2 gap-2">
                    {singleTypes.map((t) => (
                      <button
                        key={t}
                        onClick={() => handlePickType(t)}
                        disabled={mutation.isPending}
                        className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-left text-sm hover:bg-muted transition-colors disabled:opacity-50"
                      >
                        <i className={`ti ${TYPE_ICONS[t] ?? "ti-file"} text-muted-foreground`} />
                        <span className="font-mono text-[12px]">{t}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">Custom sources (multiple allowed)</p>
                <div className="grid grid-cols-2 gap-2">
                  {multiTypes.map((t) => (
                    <button
                      key={t}
                      onClick={() => handlePickType(t)}
                      className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-left text-sm hover:bg-muted transition-colors"
                    >
                      <i className={`ti ${TYPE_ICONS[t] ?? "ti-file"} text-muted-foreground`} />
                      <span className="font-mono text-[12px]">{t}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {selectedType === "webpage" ? (
                <WebpageConfigForm cfg={webCfg} setCfg={setWebCfg} />
              ) : (
                <RestConfigForm cfg={restCfg} setCfg={setRestCfg} />
              )}
              <div className="flex justify-between pt-1">
                <Button variant="ghost" size="sm" onClick={() => setStep("pick")}>
                  ← Back
                </Button>
                <Button
                  size="sm"
                  onClick={handleSubmitConfig}
                  disabled={!configValid || mutation.isPending}
                >
                  {mutation.isPending ? "Adding…" : "Add source"}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
