// Settings: API connection + generation provider/model. Author: Al Amin Ahamed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  getHealth,
  getLlmConfig,
  getOllamaModels,
  resetEmbeddingConfig,
  resetLlmConfig,
  updateEmbeddingConfig,
  updateLlmConfig,
} from "@/api/admin";
import type { OllamaModels } from "@/types/api";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { getApiBase, getToken, setApiBase, setToken } from "@/lib/config";
import { extractErrorMessage } from "@/lib/queryClient";

export function SettingsPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Settings"
        description="API connection, generation provider, and embeddings."
      />
      <ConnectionCard />
      <GenerationCard />
      <EmbeddingCard />
    </div>
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
        <p className="mt-1 text-xs text-warning">Ollama unreachable at {ollama.base_url}</p>
      )}
    </Field>
  );
}

function ConnectionCard() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [api, setApi] = useState(getApiBase());
  const [token, setTok] = useState(getToken());
  const [testing, setTesting] = useState(false);

  function save() {
    setApiBase(api.trim());
    setToken(token.trim());
    void queryClient.invalidateQueries();
    toast.ok("Settings saved.");
  }

  async function test() {
    setApiBase(api.trim());
    setToken(token.trim());
    setTesting(true);
    try {
      const health = await getHealth();
      if (health.status === "ok") toast.ok("Connected — service healthy.");
      else
        toast.info(`Reachable but ${health.status} (db ${health.database}, redis ${health.redis}).`);
    } catch {
      toast.err("Could not reach the API at that URL.");
    } finally {
      setTesting(false);
    }
  }

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Connection</CardTitle>
      </CardHeader>
      <CardContent>
        <Field label="API base URL">
          <Input
            value={api}
            onChange={(e) => setApi(e.target.value)}
            placeholder="http://localhost:8000"
          />
        </Field>
        <Field
          label="Admin bearer token"
          hint="Stored in this browser only. Required for /api/v1/admin/* endpoints."
        >
          <Input type="password" value={token} onChange={(e) => setTok(e.target.value)} />
        </Field>
        <div className="flex gap-2">
          <Button onClick={save}>Save</Button>
          <Button variant="secondary" onClick={test} disabled={testing}>
            {testing ? "Testing…" : "Test connection"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function GenerationCard() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: ["llm-config"], queryFn: getLlmConfig });
  const ollama = useQuery({ queryKey: ["ollama-models"], queryFn: getOllamaModels });

  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");

  // Seed the form once config loads.
  useEffect(() => {
    if (config.data) {
      setProvider(config.data.provider);
      setModel(config.data.model);
    }
  }, [config.data]);

  function onProvider(next: string) {
    setProvider(next);
    // Prefill the model with the chosen provider's env default.
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

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Generation</CardTitle>
      </CardHeader>
      <CardContent>
        {config.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : config.isError ? (
          <ErrorState message={extractErrorMessage(config.error)} />
        ) : (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Active</span>
              <Badge variant="accent">{current!.provider}</Badge>
              <span className="font-mono text-[13px]">{current!.model}</span>
              <Badge variant={current!.source === "override" ? "warning" : "secondary"}>
                {current!.source === "override" ? "overridden" : "from .env"}
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
              <p className="mb-3 text-sm text-warning">
                This provider has no credentials configured — generation will fail open until set.
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
          </>
        )}
      </CardContent>
    </Card>
  );
}

function EmbeddingCard() {
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
      toast.ok(`Embeddings set to ${data.embedding.provider} · ${data.embedding.model}`);
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const reset = useMutation({
    mutationFn: resetEmbeddingConfig,
    onSuccess: (data) => {
      queryClient.setQueryData(["llm-config"], data);
      setProvider(data.embedding.provider);
      setModel(data.embedding.model);
      toast.ok("Reverted embeddings to environment defaults.");
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const selected = embedding?.providers.find((p) => p.name === provider);
  const dirty = embedding
    ? provider !== embedding.provider || model.trim() !== embedding.model
    : false;

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Embeddings</CardTitle>
      </CardHeader>
      <CardContent>
        {config.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : config.isError || !embedding ? (
          <ErrorState message={extractErrorMessage(config.error)} />
        ) : (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Active</span>
              <Badge variant="accent">{embedding.provider}</Badge>
              <span className="font-mono text-[13px]">{embedding.model}</span>
              <Badge variant="secondary">{embedding.dimensions} dims</Badge>
              <Badge variant={embedding.source === "override" ? "warning" : "secondary"}>
                {embedding.source === "override" ? "overridden" : "from .env"}
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
              <p className="mb-3 text-sm text-warning">
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
          </>
        )}
      </CardContent>
    </Card>
  );
}
