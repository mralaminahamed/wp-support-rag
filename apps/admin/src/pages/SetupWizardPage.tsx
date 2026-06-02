// First-run setup wizard: generation → embeddings → first plugin. Author: Al Amin Ahamed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  completeSetup,
  getLlmConfig,
  getOllamaModels,
  ingestAll,
  ingestPlugin,
  registerPlugin,
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
import type { LLMConfig, OllamaModels } from "@/types/api";
import { SOURCE_TYPES } from "@/types/api";

type Step = 1 | 2 | 3;

const STEP_LABELS = ["Generation", "Embeddings", "First Plugin"];

// ---------------------------------------------------------------------------
// Stepper
// ---------------------------------------------------------------------------

function Stepper({ current }: { current: Step }) {
  return (
    <div className="flex items-center">
      {STEP_LABELS.map((label, i) => {
        const n = (i + 1) as Step;
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
  { icon: "ti-robot", text: "Choose your AI generation provider and model." },
  { icon: "ti-database", text: "Configure the embedding model for semantic search." },
  { icon: "ti-puzzle", text: "Register your first plugin to start ingesting docs." },
];

function LeftPanel({ step }: { step: Step }) {
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
            <div className="text-[9px] font-bold text-primary tracking-[1.5px] uppercase mt-1">
              Setup Wizard
            </div>
          </div>
        </div>

        <h1 className="text-2xl font-bold text-white leading-tight mb-2">
          Let's get you set up
        </h1>
        <p className="text-sm text-[#4b6284] leading-relaxed">
          Configure your AI providers and add your first plugin in three steps.
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
                      ? "text-[#c8d8ed]"
                      : done
                        ? "text-[#4b6284]"
                        : "text-[#2e4060]",
                  )}
                >
                  {text}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <p className="relative text-[11px] text-[#2e4060]">
        You can update the provider configuration via environment variables.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

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

function InlineError({ message }: { message: string }) {
  return (
    <p className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
      <i className="ti ti-alert-circle shrink-0" /> {message}
    </p>
  );
}

// ---------------------------------------------------------------------------
// Step 1: Generation provider
// ---------------------------------------------------------------------------

function Step1Generation({
  config,
  ollama,
  provider,
  model,
  onProvider,
  onModel,
  error,
  pending,
  onNext,
}: {
  config: LLMConfig | undefined;
  ollama: OllamaModels | undefined;
  provider: string;
  model: string;
  onProvider: (p: string) => void;
  onModel: (m: string) => void;
  error: string | null;
  pending: boolean;
  onNext: () => void;
}) {
  const selected = config?.providers.find((p) => p.name === provider);

  if (!config) return <Skeleton className="h-64 w-full" />;

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
          <Select value={provider} onValueChange={onProvider}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {config.providers.map((p) => (
                <SelectItem key={p.name} value={p.name}>
                  {p.name}
                  {p.name === config.default_provider ? " (default)" : ""}
                  {p.configured ? "" : " — not configured"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        {provider !== "ollama" && (
          <p className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            <i className="ti ti-info-circle mr-1" />
            {provider === "anthropic" ? "Anthropic" : "OpenAI"} credentials are
            configured via{" "}
            <code className="font-mono">
              WPRAG_{provider.toUpperCase()}_API_KEY
            </code>{" "}
            in your environment.
          </p>
        )}

        <ModelField
          hint={selected ? `Env default: ${selected.default_model}` : undefined}
          value={model}
          onChange={onModel}
          placeholder={selected?.default_model}
          isOllama={provider === "ollama"}
          listId="ollama-gen-models"
          ollama={ollama}
        />

        {selected && !selected.configured && (
          <p className="text-sm text-warning">
            This provider has no credentials configured — generation will fail
            until set in the environment.
          </p>
        )}

        {error && <InlineError message={error} />}
      </div>

      <div className="flex justify-end">
        <Button onClick={onNext} disabled={pending || !model.trim()}>
          {pending ? "Saving…" : "Next"}
          {!pending && <i className="ti ti-arrow-right ml-1.5 text-sm" />}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2: Embeddings
// ---------------------------------------------------------------------------

function Step2Embeddings({
  config,
  ollama,
  provider,
  model,
  onProvider,
  onModel,
  error,
  pending,
  onBack,
  onNext,
}: {
  config: LLMConfig | undefined;
  ollama: OllamaModels | undefined;
  provider: string;
  model: string;
  onProvider: (p: string) => void;
  onModel: (m: string) => void;
  error: string | null;
  pending: boolean;
  onBack: () => void;
  onNext: () => void;
}) {
  const embedding = config?.embedding;
  const selected = embedding?.providers.find((p) => p.name === provider);

  if (!config || !embedding) return <Skeleton className="h-64 w-full" />;

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
          <Select value={provider} onValueChange={onProvider}>
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
          onChange={onModel}
          placeholder={selected?.default_model}
          isOllama={provider === "ollama"}
          listId="ollama-embed-models"
          ollama={ollama}
        />

        {selected && !selected.applicable && (
          <p className="text-sm text-warning">
            {selected.dimensions} dims ≠ current {embedding.dimensions}. Set
            WPRAG_EMBEDDING_PROVIDER, run migrations, and re-ingest to switch
            width.
          </p>
        )}

        {error && <InlineError message={error} />}
      </div>

      <div className="flex justify-between">
        <Button variant="ghost" onClick={onBack}>
          <i className="ti ti-arrow-left mr-1.5 text-sm" /> Back
        </Button>
        <Button onClick={onNext} disabled={pending || !model.trim()}>
          {pending ? "Saving…" : "Next"}
          {!pending && <i className="ti ti-arrow-right ml-1.5 text-sm" />}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3: First plugin
// ---------------------------------------------------------------------------

function Step3Plugin({
  slug,
  name,
  wporgSlug,
  githubRepo,
  types,
  onSlug,
  onName,
  onWporgSlug,
  onGithubRepo,
  onToggleType,
  error,
  phase,
  onBack,
  onFinish,
}: {
  slug: string;
  name: string;
  wporgSlug: string;
  githubRepo: string;
  types: string[];
  onSlug: (v: string) => void;
  onName: (v: string) => void;
  onWporgSlug: (v: string) => void;
  onGithubRepo: (v: string) => void;
  onToggleType: (t: string) => void;
  error: string | null;
  phase: "idle" | "registering" | "completing";
  onBack: () => void;
  onFinish: (e: React.FormEvent) => void;
}) {
  const pending = phase !== "idle";

  return (
    <form onSubmit={onFinish} className="space-y-5">
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
            onChange={(e) => onSlug(e.target.value)}
            placeholder="my-plugin"
            required
          />
        </Field>
        <Field label="Name">
          <Input
            value={name}
            onChange={(e) => onName(e.target.value)}
            placeholder="My Plugin"
            required
          />
        </Field>
        <Field label="WordPress.org slug" hint="Optional — enables wp.org sources.">
          <Input
            value={wporgSlug}
            onChange={(e) => onWporgSlug(e.target.value)}
            placeholder="my-plugin"
          />
        </Field>
        <Field label="GitHub repo" hint="Optional — owner/name format.">
          <Input
            value={githubRepo}
            onChange={(e) => onGithubRepo(e.target.value)}
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
                  onChange={() => onToggleType(type)}
                />
                <span className="font-mono text-[13px]">{type}</span>
              </label>
            ))}
          </div>
        </div>

        {error && <InlineError message={error} />}
      </div>

      <div className="flex justify-between">
        <Button type="button" variant="ghost" onClick={onBack} disabled={pending}>
          <i className="ti ti-arrow-left mr-1.5 text-sm" /> Back
        </Button>
        <Button
          type="submit"
          disabled={pending || !slug.trim() || !name.trim()}
        >
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

// ---------------------------------------------------------------------------
// SetupWizardPage
// ---------------------------------------------------------------------------

export function SetupWizardPage() {
  const [step, setStep] = useState<Step>(1);

  // Step 1
  const [genProvider, setGenProvider] = useState("");
  const [genModel, setGenModel] = useState("");

  // Step 2
  const [embedProvider, setEmbedProvider] = useState("");
  const [embedModel, setEmbedModel] = useState("");

  // Step 3
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [wporgSlug, setWporgSlug] = useState("");
  const [githubRepo, setGithubRepo] = useState("");
  const [types, setTypes] = useState<string[]>(["wporg_faq", "wporg_changelog"]);

  const [error, setError] = useState<string | null>(null);
  const [step3Phase, setStep3Phase] = useState<"idle" | "registering" | "completing">("idle");

  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: ["llm-config"], queryFn: getLlmConfig });
  const ollama = useQuery({ queryKey: ["ollama-models"], queryFn: getOllamaModels });

  useEffect(() => {
    if (!config.data) return;
    if (!genProvider) {
      setGenProvider(config.data.provider);
      setGenModel(config.data.model);
    }
    if (!embedProvider && config.data.embedding) {
      setEmbedProvider(config.data.embedding.provider);
      setEmbedModel(config.data.embedding.model);
    }
  }, [config.data, genProvider, embedProvider]);

  const saveGen = useMutation({
    mutationFn: () =>
      updateLlmConfig({ provider: genProvider, model: genModel.trim() || null }),
    onSuccess: () => {
      setError(null);
      setStep(2);
    },
    onError: (e) => setError(extractErrorMessage(e)),
  });

  const saveEmbed = useMutation({
    mutationFn: () =>
      updateEmbeddingConfig({
        provider: embedProvider,
        model: embedModel.trim() || null,
      }),
    onSuccess: () => {
      ingestAll().catch(() => undefined);
      setError(null);
      setStep(3);
    },
    onError: (e) => setError(extractErrorMessage(e)),
  });

  function toggleType(type: string) {
    setTypes((cur) =>
      cur.includes(type) ? cur.filter((t) => t !== type) : [...cur, type],
    );
  }

  async function handleFinish(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setStep3Phase("registering");
      await registerPlugin({
        slug: slug.trim(),
        name: name.trim(),
        wporg_slug: wporgSlug.trim() || null,
        github_repo: githubRepo.trim() || null,
        source_types: types,
      });
      ingestPlugin(slug.trim()).catch(() => undefined);
      setStep3Phase("completing");
      await completeSetup();
      await queryClient.invalidateQueries({ queryKey: ["setup-status"] });
      navigate("/", { replace: true, state: { setupComplete: true } });
    } catch (err) {
      setError(extractErrorMessage(err));
      setStep3Phase("idle");
    }
  }

  return (
    <div className="flex min-h-screen" style={{ backgroundColor: "var(--background)" }}>
      <LeftPanel step={step} />
      <div className="flex flex-1 items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-[440px] space-y-8">
          <Stepper current={step} />
          {step === 1 && (
            <Step1Generation
              config={config.data}
              ollama={ollama.data}
              provider={genProvider}
              model={genModel}
              onProvider={(p) => {
                setGenProvider(p);
                const info = config.data?.providers.find((x) => x.name === p);
                if (info) setGenModel(info.default_model);
              }}
              onModel={setGenModel}
              error={error}
              pending={saveGen.isPending}
              onNext={() => {
                setError(null);
                saveGen.mutate();
              }}
            />
          )}
          {step === 2 && (
            <Step2Embeddings
              config={config.data}
              ollama={ollama.data}
              provider={embedProvider}
              model={embedModel}
              onProvider={(p) => {
                setEmbedProvider(p);
                const info = config.data?.embedding?.providers.find(
                  (x) => x.name === p,
                );
                if (info) setEmbedModel(info.default_model);
              }}
              onModel={setEmbedModel}
              error={error}
              pending={saveEmbed.isPending}
              onBack={() => {
                setError(null);
                setStep(1);
              }}
              onNext={() => {
                setError(null);
                saveEmbed.mutate();
              }}
            />
          )}
          {step === 3 && (
            <Step3Plugin
              slug={slug}
              name={name}
              wporgSlug={wporgSlug}
              githubRepo={githubRepo}
              types={types}
              onSlug={setSlug}
              onName={setName}
              onWporgSlug={setWporgSlug}
              onGithubRepo={setGithubRepo}
              onToggleType={toggleType}
              error={error}
              phase={step3Phase}
              onBack={() => {
                setError(null);
                setStep(2);
              }}
              onFinish={handleFinish}
            />
          )}
        </div>
      </div>
    </div>
  );
}
