// Playground: run a query (optionally streamed) and submit feedback. Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import { Send, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { listPlugins } from "@/api/admin";
import { postFeedback, postQuery, streamQuery } from "@/api/query";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState, Spinner } from "@/components/ui/feedback";
import { Field, Select, Textarea } from "@/components/ui/field";
import { extractErrorMessage } from "@/lib/queryClient";
import type { SourceRef } from "@/types/api";

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
      <h2 className="mb-5 text-xl font-semibold">Playground</h2>

      <Card className="mb-5">
        <CardBody>
          <Field label="Question">
            <Textarea
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="How do I duplicate a menu?"
            />
          </Field>
          <div className="flex flex-wrap items-end gap-4">
            <div className="min-w-50 flex-1">
              <Field label="Plugin (optional — routes when blank)">
                <Select value={slug} onChange={(e) => setSlug(e.target.value)}>
                  <option value="">Auto-route</option>
                  {plugins.data?.map((p) => (
                    <option key={p.slug} value={p.slug}>
                      {p.slug}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <label className="mb-3.5 flex items-center gap-2 text-sm text-muted">
              <input
                type="checkbox"
                className="h-4 w-4 accent-accent"
                checked={streaming}
                onChange={(e) => setStreaming(e.target.checked)}
              />
              Stream
            </label>
            <Button className="mb-3.5" onClick={run} disabled={busy}>
              {busy ? <Spinner className="border-accent-fg/40 border-t-accent-fg" /> : <Send className="h-4 w-4" />}
              Ask
            </Button>
          </div>
        </CardBody>
      </Card>

      {(busy || result || live) && (
        <Card>
          <CardBody>
            {result && (
              <div className="mb-3 flex flex-wrap gap-2">
                {result.declined && <Badge tone="warn">declined</Badge>}
                {result.degraded && <Badge tone="warn">degraded</Badge>}
                {result.cached && <Badge tone="accent">cached</Badge>}
                <Badge tone="neutral">{result.latency_ms} ms</Badge>
              </div>
            )}
            <p className="answer whitespace-pre-wrap leading-relaxed">
              {result ? result.answer : live || <span className="text-muted">Generating…</span>}
            </p>

            {result && result.sources.length > 0 && (
              <div className="mt-4">
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Sources</p>
                {result.sources.map((s) => (
                  <a
                    key={s.url}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block border-b border-border py-1.5 text-sm"
                  >
                    {s.cited && <span className="mr-1.5 text-ok">✓</span>}
                    {s.heading_path ? `${s.heading_path} — ${s.url}` : s.url}
                  </a>
                ))}
              </div>
            )}

            {result && !result.declined && (
              <div className="mt-4 flex items-center gap-2 text-sm text-muted">
                <span>Was this helpful?</span>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={feedbackSent}
                  onClick={() => sendFeedback("helpful")}
                >
                  <ThumbsUp className="h-3.5 w-3.5" /> Yes
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={feedbackSent}
                  onClick={() => sendFeedback("not_helpful")}
                >
                  <ThumbsDown className="h-3.5 w-3.5" /> No
                </Button>
              </div>
            )}
          </CardBody>
        </Card>
      )}

      {!busy && !result && !live && (
        <EmptyState title="Ask a question" hint="Answers are grounded in the ingested docs." />
      )}
    </div>
  );
}
