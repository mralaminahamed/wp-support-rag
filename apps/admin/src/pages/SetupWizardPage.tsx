// First-run setup wizard: network → admin → generation → embeddings → plugin.
// Each step is a sub-route under /setup/*. Author: Al Amin Ahamed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  completeSetup,
  getLlmConfig,
  getOllamaModels,
  getSetupNetwork,
  getSetupStatus,
  ingestAll,
  ingestPlugin,
  registerPlugin,
  saveSetupNetwork,
  setupCreateAdmin,
  setupReset,
  updateEmbeddingConfig,
  updateLlmConfig,
} from "@/api/admin";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { extractErrorMessage } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import type { OllamaModels } from "@/types/api";
import { SOURCE_TYPES } from "@/types/api";

const STEP_LABELS = ["Network", "Admin", "Generation", "Embeddings", "First Plugin"];
const STEP_ROUTES = ["network", "admin", "generation", "embeddings", "plugin"];

// ---------------------------------------------------------------------------
// Stepper
// ---------------------------------------------------------------------------

function Stepper() {
  const { pathname } = useLocation();
  const idx = STEP_ROUTES.findIndex((r) => pathname.endsWith(`/${r}`));
  const current = (idx === -1 ? 0 : idx) + 1;

  return (
    <div className="flex items-center">
      {STEP_LABELS.map((label, i) => {
        const n = i + 1;
        const done = n < current;
        const active = n === current;
        return (
          <div key={n} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={cn(
                  "flex size-7 items-center justify-center rounded-full text-xs font-bold border-2 transition-colors",
                  done
                    ? "bg-primary border-primary text-white"
                    : active
                      ? "bg-primary/10 border-primary text-primary"
                      : "bg-muted border-muted-foreground/20 text-muted-foreground",
                )}
              >
                {done ? <i className="ti ti-check text-xs" /> : n}
              </div>
              <span
                className={cn(
                  "text-[10px] font-medium whitespace-nowrap",
                  active ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {label}
              </span>
            </div>
            {i < STEP_LABELS.length - 1 && (
              <div
                className={cn(
                  "h-px flex-1 mx-2 mb-5 transition-colors",
                  done ? "bg-primary" : "bg-border",
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Left panel
// ---------------------------------------------------------------------------

const STEP_SUMMARIES = [
  { icon: "ti-network", text: "Select network mode and set the admin URL." },
  { icon: "ti-shield-lock", text: "Create the super-admin account." },
  { icon: "ti-robot", text: "Choose your AI generation provider and model." },
  { icon: "ti-database", text: "Configure the embedding model for semantic search." },
  { icon: "ti-puzzle", text: "Register your first plugin to start ingesting docs." },
];

function LeftPanel() {
  const { pathname } = useLocation();
  const idx = STEP_ROUTES.findIndex((r) => pathname.endsWith(`/${r}`));
  const step = (idx === -1 ? 0 : idx) + 1;

  return (
    <div
      className="hidden lg:flex w-[360px] shrink-0 flex-col justify-between p-12 relative overflow-hidden"
      style={{ backgroundColor: "var(--nav)" }}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />
      <div className="pointer-events-none absolute -top-32 -right-32 size-64 rounded-full bg-indigo-500/20 blur-3xl" />

      <div className="relative">
        <div className="flex items-center gap-2.5 mb-10">
          <Logo size={28} />
          <div>
            <div className="text-[13px] font-bold text-[#e0eaf8] tracking-tight leading-none">
              Support RAG
            </div>
            <div className="text-[9px] font-bold text-white/50 tracking-[1.5px] uppercase mt-1">
              Setup Wizard
            </div>
          </div>
        </div>

        <h1 className="text-2xl font-bold text-white leading-tight mb-2">
          Let's get you set up
        </h1>
        <p className="text-sm text-white/55 leading-relaxed">
          Configure network access, AI providers, and add your first plugin.
        </p>

        <div className="mt-8 space-y-4">
          {STEP_SUMMARIES.map(({ icon, text }, i) => {
            const n = i + 1;
            const done = n < step;
            const active = n === step;
            return (
              <div
                key={n}
                className={cn(
                  "flex items-start gap-3 transition-opacity",
                  !active && !done && "opacity-40",
                )}
              >
                <div
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-full text-xs",
                    done
                      ? "bg-primary/30 text-primary"
                      : active
                        ? "bg-primary/20 text-primary"
                        : "bg-white/5 text-white/40",
                  )}
                >
                  {done ? (
                    <i className="ti ti-check text-xs" />
                  ) : (
                    <i className={`ti ${icon} text-xs`} />
                  )}
                </div>
                <span
                  className={cn(
                    "text-sm leading-relaxed pt-0.5",
                    active
                      ? "text-white"
                      : done
                        ? "text-white/60"
                        : "text-white/30",
                  )}
                >
                  {text}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <p className="relative text-[11px] text-white/35">
        You can update provider configuration via environment variables.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function InlineError({ message }: { message: string }) {
  return (
    <p className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
      <i className="ti ti-alert-circle shrink-0" /> {message}
    </p>
  );
}

function ModelField({
  hint,
  value,
  onChange,
  placeholder,
  isOllama,
  listId,
  ollama,
}: {
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  isOllama: boolean;
  listId: string;
  ollama?: OllamaModels;
}) {
  return (
    <Field label="Model" hint={hint}>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="font-mono text-[13px]"
        list={isOllama && ollama?.reachable ? listId : undefined}
      />
      {isOllama && ollama?.reachable && (
        <datalist id={listId}>
          {ollama.models.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      )}
      {isOllama && ollama && !ollama.reachable && (
        <p className="mt-1 text-xs text-warning">
          Ollama unreachable at {ollama.base_url}
        </p>
      )}
    </Field>
  );
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export function SetupWizardLayout() {
  const setupStatus = useQuery({
    queryKey: ["setup-status"],
    queryFn: getSetupStatus,
    staleTime: Infinity,
    retry: false,
  });

  if (setupStatus.isPending) return null;

  // If setup already complete, redirect to the app
  if (setupStatus.data?.complete) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="flex min-h-screen" style={{ backgroundColor: "var(--background)" }}>
      <LeftPanel />
      <div className="flex flex-1 items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-[460px] space-y-8">
          <Stepper />
          <Outlet />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 1: Network
// ---------------------------------------------------------------------------

export function NetworkStep() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"localhost" | "lan">("localhost");
  const [ip, setIp] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Pre-fill based on stored config and browser URL
  const networkQuery = useQuery({ queryKey: ["setup-network"], queryFn: getSetupNetwork });

  useEffect(() => {
    const browserHost = window.location.hostname;
    const onLan = browserHost !== "localhost" && browserHost !== "127.0.0.1";

    if (networkQuery.data?.admin_url) {
      const stored = networkQuery.data.admin_url;
      const extractedIp = stored.replace(/^https?:\/\//, "").replace(/\/$/, "");
      const isStoredLan = extractedIp !== "localhost" && extractedIp !== "127.0.0.1";
      setMode(isStoredLan ? "lan" : "localhost");
      setIp(isStoredLan ? extractedIp : onLan ? browserHost : "");
    } else if (onLan) {
      setMode("lan");
      setIp(browserHost);
    }
  }, [networkQuery.data]);

  async function handleNext() {
    setError(null);
    setPending(true);
    try {
      // 1. Wipe all existing data
      await setupReset();
      // 2. Save network config
      const adminUrl =
        mode === "lan"
          ? `http://${ip.trim().replace(/^https?:\/\//, "").replace(/\/$/, "")}`
          : "http://localhost";
      await saveSetupNetwork(adminUrl);
      void navigate("/setup/admin");
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setPending(false);
    }
  }

  const ipValid = mode === "localhost" || ip.trim().length > 0;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Network access</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          How will you access this admin panel?
        </p>
      </div>

      {/* Warning banner */}
      <div className="rounded-lg border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning">
        <p className="font-semibold flex items-center gap-2">
          <i className="ti ti-alert-triangle shrink-0" /> Fresh setup — all existing data will be wiped
        </p>
        <p className="mt-1 text-xs opacity-80">
          Users, plugins, queries, and settings are permanently deleted. Roles are preserved.
        </p>
      </div>

      <div className="space-y-3">
        {/* Localhost card */}
        <label
          className={cn(
            "flex items-start gap-3 rounded-lg border p-4 cursor-pointer transition-colors",
            mode === "localhost"
              ? "border-primary bg-primary/5"
              : "border-border hover:border-muted-foreground/40",
          )}
        >
          <input
            type="radio"
            name="network-mode"
            className="mt-0.5 accent-primary"
            checked={mode === "localhost"}
            onChange={() => setMode("localhost")}
          />
          <div>
            <div className="text-sm font-semibold leading-tight">Localhost only</div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              Access from this machine only (http://localhost)
            </div>
          </div>
        </label>

        {/* LAN card */}
        <label
          className={cn(
            "flex items-start gap-3 rounded-lg border p-4 cursor-pointer transition-colors",
            mode === "lan"
              ? "border-primary bg-primary/5"
              : "border-border hover:border-muted-foreground/40",
          )}
        >
          <input
            type="radio"
            name="network-mode"
            className="mt-0.5 accent-primary"
            checked={mode === "lan"}
            onChange={() => setMode("lan")}
          />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold leading-tight">LAN / remote access</div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              Access from other devices on your network
            </div>
            {mode === "lan" && (
              <div className="mt-3">
                <Input
                  value={ip}
                  onChange={(e) => setIp(e.target.value)}
                  placeholder="192.168.1.100"
                  className="font-mono text-[13px]"
                  onClick={(e) => e.preventDefault()}
                />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  IP or hostname of this server on your network
                </p>
              </div>
            )}
          </div>
        </label>
      </div>

      {/* Confirmation checkbox */}
      <label className="flex items-start gap-2.5 cursor-pointer">
        <input
          type="checkbox"
          className="mt-0.5 size-4 accent-primary"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        <span className="text-sm text-muted-foreground">
          I understand all existing data will be permanently deleted
        </span>
      </label>

      {error && <InlineError message={error} />}

      <div className="flex justify-end">
        <Button
          onClick={() => void handleNext()}
          disabled={pending || !confirmed || !ipValid}
        >
          {pending ? "Setting up…" : "Start fresh setup"}
          {!pending && <i className="ti ti-arrow-right ml-1.5 text-sm" />}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2: Admin account
// ---------------------------------------------------------------------------

export function AdminStep() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleNext() {
    setError(null);
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setPending(true);
    try {
      await setupCreateAdmin(email.trim(), password);
      // Refresh auth state so subsequent steps work
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      void navigate("/setup/generation");
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Admin account</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Create the super-admin account for this instance.
        </p>
      </div>

      <div className="space-y-4">
        <Field label="Email">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="admin@example.com"
            autoComplete="email"
          />
        </Field>

        <Field label="Password">
          <div className="relative">
            <Input
              type={showPw ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              autoComplete="new-password"
              className="pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              tabIndex={-1}
            >
              <i className={`ti ${showPw ? "ti-eye-off" : "ti-eye"} text-sm`} />
            </button>
          </div>
        </Field>

        <Field label="Confirm password">
          <Input
            type={showPw ? "text" : "password"}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Repeat password"
            autoComplete="new-password"
          />
        </Field>

        {error && <InlineError message={error} />}
      </div>

      <div className="flex justify-end">
        <Button
          onClick={() => void handleNext()}
          disabled={pending || !email.trim() || password.length < 8 || !confirm}
        >
          {pending ? "Creating…" : "Next"}
          {!pending && <i className="ti ti-arrow-right ml-1.5 text-sm" />}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3: Generation provider
// ---------------------------------------------------------------------------

export function GenerationStep() {
  const navigate = useNavigate();
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [error, setError] = useState<string | null>(null);

  const config = useQuery({ queryKey: ["llm-config"], queryFn: getLlmConfig });
  const ollama = useQuery({ queryKey: ["ollama-models"], queryFn: getOllamaModels });

  useEffect(() => {
    if (!config.data || provider) return;
    setProvider(config.data.provider);
    setModel(config.data.model);
  }, [config.data, provider]);

  const saveGen = useMutation({
    mutationFn: () => updateLlmConfig({ provider, model: model.trim() || null }),
    onSuccess: () => {
      setError(null);
      void navigate("/setup/embeddings");
    },
    onError: (e) => setError(extractErrorMessage(e)),
  });

  const selected = config.data?.providers.find((p) => p.name === provider);

  if (!config.data) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Generation provider</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Choose the AI model that will answer support questions.
        </p>
      </div>

      <div className="space-y-4">
        <Field label="Provider">
          <Select
            value={provider}
            onValueChange={(p) => {
              setProvider(p);
              const info = config.data.providers.find((x) => x.name === p);
              if (info) setModel(info.default_model);
            }}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {config.data.providers.map((p) => (
                <SelectItem key={p.name} value={p.name}>
                  {p.name}
                  {p.name === config.data.default_provider ? " (default)" : ""}
                  {p.configured ? "" : " — not configured"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        {provider !== "ollama" && (
          <p className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            <i className="ti ti-info-circle mr-1" />
            {provider === "anthropic" ? "Anthropic" : "OpenAI"} credentials are configured via{" "}
            <code className="font-mono">
              WPRAG_{provider.toUpperCase()}_API_KEY
            </code>{" "}
            in your environment.
          </p>
        )}

        <ModelField
          hint={selected ? `Env default: ${selected.default_model}` : undefined}
          value={model}
          onChange={setModel}
          placeholder={selected?.default_model}
          isOllama={provider === "ollama"}
          listId="ollama-gen-models"
          ollama={ollama.data}
        />

        {selected && !selected.configured && (
          <p className="text-sm text-warning">
            This provider has no credentials configured — generation will fail until set.
          </p>
        )}

        {error && <InlineError message={error} />}
      </div>

      <div className="flex justify-between">
        <Button variant="ghost" onClick={() => void navigate("/setup/admin")}>
          <i className="ti ti-arrow-left mr-1.5 text-sm" /> Back
        </Button>
        <Button
          onClick={() => { setError(null); saveGen.mutate(); }}
          disabled={saveGen.isPending || !model.trim()}
        >
          {saveGen.isPending ? "Saving…" : "Next"}
          {!saveGen.isPending && <i className="ti ti-arrow-right ml-1.5 text-sm" />}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 4: Embeddings
// ---------------------------------------------------------------------------

export function EmbeddingsStep() {
  const navigate = useNavigate();
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [error, setError] = useState<string | null>(null);

  const config = useQuery({ queryKey: ["llm-config"], queryFn: getLlmConfig });
  const ollama = useQuery({ queryKey: ["ollama-models"], queryFn: getOllamaModels });

  useEffect(() => {
    if (!config.data?.embedding || provider) return;
    setProvider(config.data.embedding.provider);
    setModel(config.data.embedding.model);
  }, [config.data, provider]);

  const saveEmbed = useMutation({
    mutationFn: () => updateEmbeddingConfig({ provider, model: model.trim() || null }),
    onSuccess: () => {
      ingestAll().catch(() => undefined);
      setError(null);
      void navigate("/setup/plugin");
    },
    onError: (e) => setError(extractErrorMessage(e)),
  });

  const embedding = config.data?.embedding;
  const selected = embedding?.providers.find((p) => p.name === provider);

  if (!config.data || !embedding) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Embeddings</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Choose the model that converts text into vectors for semantic search.
        </p>
      </div>

      <div className="space-y-4">
        <Field
          label="Provider"
          hint="The vector width is bound to the index; switching width needs a migration + re-embed."
        >
          <Select
            value={provider}
            onValueChange={(p) => {
              setProvider(p);
              const info = embedding.providers.find((x) => x.name === p);
              if (info) setModel(info.default_model);
            }}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {embedding.providers.map((p) => (
                <SelectItem key={p.name} value={p.name}>
                  {p.name} · {p.dimensions} dims
                  {p.applicable ? "" : " — needs migration"}
                  {p.configured ? "" : " — not configured"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <ModelField
          hint={selected ? `Default: ${selected.default_model}` : undefined}
          value={model}
          onChange={setModel}
          placeholder={selected?.default_model}
          isOllama={provider === "ollama"}
          listId="ollama-embed-models"
          ollama={ollama.data}
        />

        {selected && !selected.applicable && (
          <p className="text-sm text-warning">
            {selected.dimensions} dims ≠ current {embedding.dimensions}. Set
            WPRAG_EMBEDDING_PROVIDER, run migrations, and re-ingest to switch width.
          </p>
        )}

        {error && <InlineError message={error} />}
      </div>

      <div className="flex justify-between">
        <Button variant="ghost" onClick={() => void navigate("/setup/generation")}>
          <i className="ti ti-arrow-left mr-1.5 text-sm" /> Back
        </Button>
        <Button
          onClick={() => { setError(null); saveEmbed.mutate(); }}
          disabled={saveEmbed.isPending || !model.trim()}
        >
          {saveEmbed.isPending ? "Saving…" : "Next"}
          {!saveEmbed.isPending && <i className="ti ti-arrow-right ml-1.5 text-sm" />}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 5: First plugin
// ---------------------------------------------------------------------------

export function PluginStep() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [wporgSlug, setWporgSlug] = useState("");
  const [githubRepo, setGithubRepo] = useState("");
  const [types, setTypes] = useState<string[]>(["wporg_faq", "wporg_changelog"]);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "registering" | "completing">("idle");

  function toggleType(type: string) {
    setTypes((cur) =>
      cur.includes(type) ? cur.filter((t) => t !== type) : [...cur, type],
    );
  }

  async function handleFinish(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setPhase("registering");
      await registerPlugin({
        slug: slug.trim(),
        name: name.trim(),
        wporg_slug: wporgSlug.trim() || null,
        github_repo: githubRepo.trim() || null,
        source_types: types,
      });
      ingestPlugin(slug.trim()).catch(() => undefined);
      setPhase("completing");
      await completeSetup();
      await queryClient.invalidateQueries({ queryKey: ["setup-status"] });
      void navigate("/", { replace: true, state: { setupComplete: true } });
    } catch (err) {
      setError(extractErrorMessage(err));
      setPhase("idle");
    }
  }

  const pending = phase !== "idle";

  return (
    <form onSubmit={(e) => void handleFinish(e)} className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight">First plugin</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Register a plugin and choose which documentation sources to ingest.
        </p>
      </div>

      <div className="space-y-4">
        <Field label="Slug" hint="URL-safe identifier, e.g. my-plugin">
          <Input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="my-plugin"
            required
          />
        </Field>
        <Field label="Name">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="My Plugin"
            required
          />
        </Field>
        <Field label="WordPress.org slug" hint="Optional — enables wp.org sources.">
          <Input
            value={wporgSlug}
            onChange={(e) => setWporgSlug(e.target.value)}
            placeholder="my-plugin"
          />
        </Field>
        <Field label="GitHub repo" hint="Optional — owner/name format.">
          <Input
            value={githubRepo}
            onChange={(e) => setGithubRepo(e.target.value)}
            placeholder="acme/my-plugin"
          />
        </Field>

        <div>
          <Label className="mb-2 block text-sm font-medium">Sources</Label>
          <div className="grid grid-cols-2 gap-2">
            {SOURCE_TYPES.map((type) => (
              <label
                key={type}
                className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer"
              >
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={types.includes(type)}
                  onChange={() => toggleType(type)}
                />
                <span className="font-mono text-[13px]">{type}</span>
              </label>
            ))}
          </div>
        </div>

        {error && <InlineError message={error} />}
      </div>

      <div className="flex justify-between">
        <Button type="button" variant="ghost" onClick={() => void navigate("/setup/embeddings")} disabled={pending}>
          <i className="ti ti-arrow-left mr-1.5 text-sm" /> Back
        </Button>
        <Button type="submit" disabled={pending || !slug.trim() || !name.trim()}>
          {phase === "registering"
            ? "Registering…"
            : phase === "completing"
              ? "Finishing…"
              : "Finish"}
          {!pending && <i className="ti ti-check ml-1.5 text-sm" />}
        </Button>
      </div>
    </form>
  );
}
