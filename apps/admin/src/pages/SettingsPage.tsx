// Settings: API connection + generation provider/model. Author: Al Amin Ahamed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getHealth, getLlmConfig, resetLlmConfig, updateLlmConfig } from "@/api/admin";
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
      <PageHeader title="Settings" description="API connection and generation provider." />
      <ConnectionCard />
      <GenerationCard />
    </div>
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

            <Field
              label="Model"
              hint={selected ? `Env default: ${selected.default_model}` : undefined}
            >
              <Input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={selected?.default_model}
                className="font-mono text-[13px]"
              />
            </Field>

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
