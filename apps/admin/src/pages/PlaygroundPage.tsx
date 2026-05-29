// Playground: run a query (optionally streamed) and submit feedback. Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, ExternalLink, Send, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { listPlugins } from "@/api/admin";
import { postFeedback, postQuery, streamQuery } from "@/api/query";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, Spinner } from "@/components/ui/feedback";
import { Markdown } from "@/components/ui/markdown";
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

const EXAMPLES = [
  "How do I install the plugin?",
  "How do I duplicate a menu?",
  "Is it compatible with the latest WordPress?",
  "How do I report a bug?",
];

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function copyAnswer(text: string): void {
  void navigator.clipboard?.writeText(text);
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
  provider: string;
  model: string;
}

export function PlaygroundPage() {
  const toast = useToast();
  const plugins = useQuery({ queryKey: ["plugins"], queryFn: listPlugins });

  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [slug, setSlug] = useState("");
  const [streaming, setStreaming] = useState(true);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(false);

  async function run(override?: string) {
    const q = (override ?? question).trim();
    if (!q || busy) return;
    if (override !== undefined) setQuestion(override);
    setBusy(true);
    setResult(null);
    setLive("");
    setFeedbackSent(false);
    setAsked(q);
    const input = { question: q, plugin_slug: slug || null };
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

  const hasOutput = busy || result || live;

  return (
    <div>
      <PageHeader
        title="Playground"
        description="Ask a question and inspect the grounded, cited answer."
      />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(320px,380px)_1fr]">
        {/* Ask panel */}
        <Card className="lg:sticky lg:top-4">
          <CardContent>
            <Field label="Question">
              <Textarea
                rows={4}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void run();
                }}
                placeholder="How do I duplicate a menu?"
              />
            </Field>

            <div className="mb-4">
              <Label className="mb-1.5 block text-xs text-muted-foreground">Try an example</Label>
              <div className="flex flex-wrap gap-1.5">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    disabled={busy}
                    onClick={() => void run(ex)}
                    className="rounded-full border bg-muted/40 px-2.5 py-1 text-xs text-muted-foreground transition hover:border-primary/40 hover:text-foreground disabled:opacity-50"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>

            <Field label="Plugin" hint="Optional — auto-routes when blank.">
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
            </Field>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={streaming}
                  onChange={(e) => setStreaming(e.target.checked)}
                />
                Stream
              </label>
              <Button onClick={() => void run()} disabled={busy || !question.trim()}>
                {busy ? <Spinner /> : <Send />}
                Ask
              </Button>
            </div>
            <p className="mt-2 text-right text-[11px] text-muted-foreground">⌘/Ctrl + Enter</p>
          </CardContent>
        </Card>

        {/* Answer pane */}
        {hasOutput ? (
          <Card>
            <CardContent>
              {asked && (
                <div className="mb-4 border-b pb-3">
                  <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Question
                  </p>
                  <p className="mt-1 font-medium">{asked}</p>
                </div>
              )}

              {result && (
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  {result.declined && <Badge variant="warning">declined</Badge>}
                  {result.degraded && <Badge variant="warning">degraded</Badge>}
                  {result.cached && <Badge variant="accent">cached</Badge>}
                  <Badge variant="secondary">
                    {result.provider} · {result.model}
                  </Badge>
                  <Badge variant="secondary">{result.latency_ms} ms</Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto"
                    onClick={() => copyAnswer(result.answer)}
                  >
                    <Copy /> Copy
                  </Button>
                </div>
              )}

              {result ? (
                <Markdown>{result.answer}</Markdown>
              ) : live ? (
                <p className="text-sm leading-relaxed whitespace-pre-wrap">
                  {live}
                  <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-primary align-text-bottom" />
                </p>
              ) : (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Spinner /> Generating…
                </p>
              )}

              {result && result.sources.length > 0 && (
                <div className="mt-5">
                  <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Sources · {result.sources.filter((s) => s.cited).length} cited
                  </p>
                  <ol className="space-y-1.5">
                    {result.sources.map((s, i) => (
                      <li key={s.url}>
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={s.url}
                          className="group flex items-center gap-2.5 rounded-md border bg-muted/30 px-3 py-2 text-sm transition hover:border-primary/40 hover:bg-muted"
                        >
                          <span
                            className={
                              s.cited
                                ? "flex size-5 shrink-0 items-center justify-center rounded-full bg-success/15 text-[11px] font-semibold text-success"
                                : "flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-medium text-muted-foreground"
                            }
                          >
                            {i + 1}
                          </span>
                          <span className="truncate text-foreground group-hover:text-primary">
                            {s.heading_path || hostOf(s.url)}
                          </span>
                          {s.cited && (
                            <span className="inline-flex items-center gap-1 text-[11px] text-success">
                              <Check className="size-3" /> cited
                            </span>
                          )}
                          <span className="ml-auto truncate font-mono text-xs text-muted-foreground">
                            {hostOf(s.url)}
                          </span>
                          <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" />
                        </a>
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {result && !result.declined && (
                <div className="mt-5 flex items-center gap-2 border-t pt-4 text-sm text-muted-foreground">
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
                  {feedbackSent && <span className="text-success">Thanks!</span>}
                </div>
              )}
            </CardContent>
          </Card>
        ) : (
          <Card className="border-dashed">
            <CardContent className="flex min-h-72 flex-col items-center justify-center text-center">
              <EmptyState
                title="Ask a question"
                hint="Answers are grounded in your ingested plugin docs, with cited sources."
              />
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
