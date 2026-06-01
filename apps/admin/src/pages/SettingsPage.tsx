// Settings: generation provider and embeddings. Author: Al Amin Ahamed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  getLlmConfig,
  getOllamaModels,
  ingestAll,
  resetEmbeddingConfig,
  resetLlmConfig,
  updateEmbeddingConfig,
  updateLlmConfig,
} from "@/api/admin";
import type { OllamaModels } from "@/types/api";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/feedback";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
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

const TABS = [
  { to: "generation", label: "Generation" },
  { to: "embeddings", label: "Embeddings" },
];

export function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-5">
      <PageHeader
        title="Settings"
        description="Generation provider and embeddings configuration."
      />

      <div className="flex border-b border-border">
        {TABS.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors cursor-pointer",
                isActive
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )
            }
          >
            {label}
          </NavLink>
        ))}
      </div>

      <Outlet />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared
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
        <p className="mt-1 text-xs text-warning">Ollama unreachable at {ollama.base_url}</p>
      )}
    </Field>
  );
}

// ---------------------------------------------------------------------------
// Generation
// ---------------------------------------------------------------------------

export function GenerationSection() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: ["llm-config"], queryFn: getLlmConfig });
  const ollama = useQuery({ queryKey: ["ollama-models"], queryFn: getOllamaModels });

  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");

  useEffect(() => {
    if (config.data) {
      setProvider(config.data.provider);
      setModel(config.data.model);
    }
  }, [config.data]);

  function onProvider(next: string) {
    setProvider(next);
    const info = config.data?.providers.find((p) => p.name === next);
    if (info) setModel(info.default_model);
  }

  const save = useMutation({
    mutationFn: () => updateLlmConfig({ provider, model: model.trim() || null }),
    onSuccess: (data) => {
      queryClient.setQueryData(["llm-config"], data);
      toast.ok(`Generation set to ${data.provider} · ${data.model}`);
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const reset = useMutation({
    mutationFn: resetLlmConfig,
    onSuccess: (data) => {
      queryClient.setQueryData(["llm-config"], data);
      setProvider(data.provider);
      setModel(data.model);
      toast.ok("Reverted to environment defaults.");
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const current = config.data;
  const selected = current?.providers.find((p) => p.name === provider);
  const dirty = current ? provider !== current.provider || model.trim() !== current.model : false;

  if (config.isLoading) return <Skeleton className="h-48 w-full" />;
  if (config.isError) return <ErrorState message={extractErrorMessage(config.error)} />;

  return (
    <Card>
      <CardContent className="pt-5 pb-5 space-y-4">
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/50 px-3.5 py-2.5 text-sm">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60 mr-1">Active</span>
          <Badge variant="accent">{current!.provider}</Badge>
          <span className="font-mono text-[12px] text-muted-foreground">{current!.model}</span>
          <Badge variant={current!.source === "override" ? "warning" : "outline"} className="ml-auto text-[10px]">
            {current!.source === "override" ? "overridden" : "env default"}
          </Badge>
        </div>

        <Field label="Provider" hint="Default and per-provider models come from the .env file.">
          <Select value={provider} onValueChange={onProvider}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {current!.providers.map((p) => (
                <SelectItem key={p.name} value={p.name}>
                  {p.name}
                  {p.name === current!.default_provider ? " (default)" : ""}
                  {p.configured ? "" : " — not configured"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

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

        <div className="flex gap-2">
          <Button onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
          <Button
            variant="secondary"
            onClick={() => reset.mutate()}
            disabled={current!.source !== "override" || reset.isPending}
          >
            Reset to .env
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Embeddings
// ---------------------------------------------------------------------------

export function EmbeddingSection() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: ["llm-config"], queryFn: getLlmConfig });
  const ollama = useQuery({ queryKey: ["ollama-models"], queryFn: getOllamaModels });
  const embedding = config.data?.embedding;

  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");

  useEffect(() => {
    if (embedding) {
      setProvider(embedding.provider);
      setModel(embedding.model);
    }
  }, [embedding]);

  function onProvider(next: string) {
    setProvider(next);
    const info = embedding?.providers.find((p) => p.name === next);
    if (info) setModel(info.default_model);
  }

  const save = useMutation({
    mutationFn: () => updateEmbeddingConfig({ provider, model: model.trim() || null }),
    onSuccess: (data) => {
      queryClient.setQueryData(["llm-config"], data);
      toast.ok(`Embeddings set to ${data.embedding.provider} · ${data.embedding.model}. Re-ingestion queued.`);
      ingestAll().catch(() => undefined);
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const reset = useMutation({
    mutationFn: resetEmbeddingConfig,
    onSuccess: (data) => {
      queryClient.setQueryData(["llm-config"], data);
      setProvider(data.embedding.provider);
      setModel(data.embedding.model);
      toast.ok("Reverted embeddings to environment defaults. Re-ingestion queued.");
      ingestAll().catch(() => undefined);
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const selected = embedding?.providers.find((p) => p.name === provider);
  const dirty = embedding
    ? provider !== embedding.provider || model.trim() !== embedding.model
    : false;

  if (config.isLoading) return <Skeleton className="h-48 w-full" />;
  if (config.isError || !embedding) return <ErrorState message={extractErrorMessage(config.error)} />;

  return (
    <Card>
      <CardContent className="pt-5 pb-5 space-y-4">
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/50 px-3.5 py-2.5 text-sm">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60 mr-1">Active</span>
          <Badge variant="accent">{embedding.provider}</Badge>
          <span className="font-mono text-[12px] text-muted-foreground">{embedding.model}</span>
          <Badge variant="secondary" className="text-[10px]">{embedding.dimensions}d</Badge>
          <Badge variant={embedding.source === "override" ? "warning" : "outline"} className="ml-auto text-[10px]">
            {embedding.source === "override" ? "overridden" : "env default"}
          </Badge>
        </div>

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

        <div className="flex gap-2">
          <Button onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
          <Button
            variant="secondary"
            onClick={() => reset.mutate()}
            disabled={embedding.source !== "override" || reset.isPending}
          >
            Reset to .env
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
