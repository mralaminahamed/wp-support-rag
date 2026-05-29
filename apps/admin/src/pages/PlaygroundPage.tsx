// Playground: run a query (optionally streamed) and submit feedback. Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import { Check, ExternalLink, Send, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { listPlugins } from "@/api/admin";
import { postFeedback, postQuery, streamQuery } from "@/api/query";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, Spinner } from "@/components/ui/feedback";
import { Field } from "@/components/ui/field";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { extractErrorMessage } from "@/lib/queryClient";
import { PageHeader } from "@/components/ui/page-header";
import type { SourceRef } from "@/types/api";

const ROUTE = "__route__";

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

interface Result {
  query_id: string;
  answer: string;
  citations: string[];
  sources: SourceRef[];
  cached: boolean;
  degraded: boolean;
  declined: boolean;
  latency_ms: number;
}

export function PlaygroundPage() {
  const toast = useToast();
  const plugins = useQuery({ queryKey: ["plugins"], queryFn: listPlugins });

  const [question, setQuestion] = useState("");
  const [slug, setSlug] = useState("");
  const [streaming, setStreaming] = useState(true);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(false);

  async function run() {
    if (!question.trim()) return;
    setBusy(true);
    setResult(null);
    setLive("");
    setFeedbackSent(false);
    const input = { question: question.trim(), plugin_slug: slug || null };
    try {
      if (streaming) {
        const done = await streamQuery(input, (t) => setLive((cur) => cur + t));
        setResult(done);
        setLive("");
      } else {
        setResult(await postQuery(input));
      }
    } catch (error) {
      toast.err(extractErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function sendFeedback(rating: "helpful" | "not_helpful") {
    if (!result) return;
    try {
      await postFeedback(result.query_id, rating);
      setFeedbackSent(true);
      toast.ok("Thanks for the feedback.");
    } catch (error) {
      toast.err(extractErrorMessage(error));
    }
  }

  return (
    <div>
      <PageHeader
        title="Playground"
        description="Ask a question and inspect the grounded, cited answer."
      />

      <Card className="mb-5">
        <CardContent>
          <Field label="Question">
            <Textarea
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="How do I duplicate a menu?"
            />
          </Field>
          <div className="flex flex-wrap items-end gap-4">
            <div className="grid min-w-52 flex-1 gap-1.5">
              <Label>Plugin (optional — routes when blank)</Label>
              <Select value={slug || ROUTE} onValueChange={(v) => setSlug(v === ROUTE ? "" : v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ROUTE}>Auto-route</SelectItem>
                  {plugins.data?.map((p) => (
                    <SelectItem key={p.slug} value={p.slug}>
                      {p.slug}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <label className="flex items-center gap-2 pb-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={streaming}
                onChange={(e) => setStreaming(e.target.checked)}
              />
              Stream
            </label>
            <Button onClick={run} disabled={busy}>
              {busy ? <Spinner /> : <Send />}
              Ask
            </Button>
          </div>
        </CardContent>
      </Card>

      {(busy || result || live) && (
        <Card>
          <CardContent>
            {result && (
              <div className="mb-3 flex flex-wrap gap-2">
                {result.declined && <Badge variant="warning">declined</Badge>}
                {result.degraded && <Badge variant="warning">degraded</Badge>}
                {result.cached && <Badge variant="accent">cached</Badge>}
                <Badge variant="secondary">{result.latency_ms} ms</Badge>
              </div>
            )}
            <p className="leading-relaxed whitespace-pre-wrap">
              {result ? (
                result.answer
              ) : live ? (
                live
              ) : (
                <span className="text-muted-foreground">Generating…</span>
              )}
            </p>

            {result && result.sources.length > 0 && (
              <div className="mt-4">
                <p className="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                  Sources
                </p>
                <ul className="divide-y">
                  {result.sources.map((s) => (
                    <li key={s.url}>
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={s.url}
                        className="group flex items-center gap-2 py-1.5 text-sm"
                      >
                        {s.cited ? (
                          <Check className="size-3.5 shrink-0 text-success" />
                        ) : (
                          <span className="size-3.5 shrink-0" />
                        )}
                        <span className="truncate text-foreground group-hover:text-primary group-hover:underline">
                          {s.heading_path || hostOf(s.url)}
                        </span>
                        <span className="ml-auto truncate font-mono text-xs text-muted-foreground">
                          {hostOf(s.url)}
                        </span>
                        <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" />
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {result && !result.declined && (
              <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                <span>Was this helpful?</span>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={feedbackSent}
                  onClick={() => sendFeedback("helpful")}
                >
                  <ThumbsUp /> Yes
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={feedbackSent}
                  onClick={() => sendFeedback("not_helpful")}
                >
                  <ThumbsDown /> No
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {!busy && !result && !live && (
        <EmptyState title="Ask a question" hint="Answers are grounded in the ingested docs." />
      )}
    </div>
  );
}
