// Settings: API base URL + admin token + connection test. Author: Al Amin Ahamed.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getHealth } from "@/api/admin";
import { useToast } from "@/components/ToastProvider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { getApiBase, getToken, setApiBase, setToken } from "@/lib/config";

export function SettingsPage() {
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
    <div>
      <PageHeader title="Settings" description="API connection and admin authentication." />
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
    </div>
  );
}
