// Playground: chat-style grounded Q&A. Each turn is an independent RAG query
// (no conversation memory is sent to the model). Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  Copy,
  ExternalLink,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  User,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { listPlugins } from "@/api/admin";
import { postFeedback, postQuery, streamQuery } from "@/api/query";
import { Logo } from "@/components/Logo";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/feedback";
import { Markdown } from "@/components/ui/markdown";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { extractErrorMessage } from "@/lib/queryClient";
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

function copyText(text: string): void {
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

interface Turn {
  id: string;
  question: string;
  live: string;
  result: Result | null;
  error: string | null;
  feedbackSent: boolean;
}

export function PlaygroundPage() {
  const toast = useToast();
  const plugins = useQuery({ queryKey: ["plugins"], queryFn: listPlugins });

  const [messages, setMessages] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [slug, setSlug] = useState("");
  const [streaming, setStreaming] = useState(true);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function patch(id: string, change: Partial<Turn>) {
    setMessages((m) => m.map((t) => (t.id === id ? { ...t, ...change } : t)));
  }

  async function run(override?: string) {
    const q = (override ?? input).trim();
    if (!q || busy) return;
    setInput("");
    const id = crypto.randomUUID();
    setMessages((m) => [
      ...m,
      { id, question: q, live: "", result: null, error: null, feedbackSent: false },
    ]);
    setBusy(true);
    const reqInput = { question: q, plugin_slug: slug || null };
    try {
      if (streaming) {
        const done = await streamQuery(reqInput, (t) =>
          setMessages((m) => m.map((x) => (x.id === id ? { ...x, live: x.live + t } : x))),
        );
        patch(id, { result: done, live: "" });
      } else {
        patch(id, { result: await postQuery(reqInput) });
      }
    } catch (error) {
      const msg = extractErrorMessage(error);
      patch(id, { error: msg });
      toast.err(msg);
    } finally {
      setBusy(false);
    }
  }

  async function sendFeedback(turn: Turn, rating: "helpful" | "not_helpful") {
    if (!turn.result) return;
    try {
      await postFeedback(turn.result.query_id, rating);
      patch(turn.id, { feedbackSent: true });
      toast.ok("Thanks for the feedback.");
    } catch (error) {
      toast.err(extractErrorMessage(error));
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100dvh-7rem)] max-w-3xl flex-col">
      <div className="flex-1 space-y-6 overflow-y-auto pb-4">
        {messages.length === 0 ? (
          <Greeting onPick={(q) => void run(q)} disabled={busy} />
        ) : (
          messages.map((turn) => (
            <div key={turn.id} className="space-y-4">
              <UserBubble text={turn.question} />
              <AssistantMessage turn={turn} onFeedback={sendFeedback} />
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      <Composer
        value={input}
        onChange={setInput}
        onSend={() => void run()}
        busy={busy}
        slug={slug}
        onSlug={setSlug}
        streaming={streaming}
        onStreaming={setStreaming}
        pluginSlugs={plugins.data?.map((p) => p.slug) ?? []}
      />
    </div>
  );
}

function Greeting({ onPick, disabled }: { onPick: (q: string) => void; disabled: boolean }) {
  return (
    <div className="flex h-full flex-col items-center justify-center py-12 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10">
        <Sparkles className="size-6 text-primary" />
      </div>
      <h2 className="mt-4 text-xl font-semibold tracking-tight">Ask about your plugins</h2>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">
        Answers are grounded in your ingested plugin docs and cite their sources. Each question is
        answered independently.
      </p>
      <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            disabled={disabled}
            onClick={() => onPick(ex)}
            className="rounded-full border bg-card px-3 py-1.5 text-sm text-muted-foreground transition hover:border-primary/40 hover:text-foreground disabled:opacity-50"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end gap-3">
      <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
        {text}
      </div>
      <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <User className="size-4" />
      </div>
    </div>
  );
}

function AssistantMessage({
  turn,
  onFeedback,
}: {
  turn: Turn;
  onFeedback: (turn: Turn, rating: "helpful" | "not_helpful") => void;
}) {
  const { result, live, error } = turn;
  return (
    <div className="flex gap-3">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <Logo size={18} />
      </div>
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm border bg-card px-4 py-3">
        {error ? (
          <p className="flex items-center gap-2 text-sm text-warning">
            <AlertTriangle className="size-4" /> {error}
          </p>
        ) : result ? (
          <>
            <div className="mb-2 flex flex-wrap items-center gap-2">
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
                onClick={() => copyText(result.answer)}
              >
                <Copy /> Copy
              </Button>
            </div>

            <Markdown>{result.answer}</Markdown>

            {result.sources.length > 0 && (
              <div className="mt-4">
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

            {!result.declined && (
              <div className="mt-3 flex items-center gap-2 border-t pt-3 text-sm text-muted-foreground">
                <span>Was this helpful?</span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Yes"
                  disabled={turn.feedbackSent}
                  onClick={() => onFeedback(turn, "helpful")}
                >
                  <ThumbsUp />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="No"
                  disabled={turn.feedbackSent}
                  onClick={() => onFeedback(turn, "not_helpful")}
                >
                  <ThumbsDown />
                </Button>
                {turn.feedbackSent && <span className="text-success">Thanks!</span>}
              </div>
            )}
          </>
        ) : live ? (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {live}
            <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-primary align-text-bottom" />
          </p>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Spinner /> Thinking…
          </p>
        )}
      </div>
    </div>
  );
}

function Composer({
  value,
  onChange,
  onSend,
  busy,
  slug,
  onSlug,
  streaming,
  onStreaming,
  pluginSlugs,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  slug: string;
  onSlug: (v: string) => void;
  streaming: boolean;
  onStreaming: (v: boolean) => void;
  pluginSlugs: string[];
}) {
  return (
    <div className="border-t bg-background pt-3">
      <div className="rounded-2xl border bg-card p-2 shadow-sm focus-within:border-primary/40">
        <Textarea
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          placeholder="How do I duplicate a menu?"
          className="max-h-40 min-h-9 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
        />
        <div className="flex items-center gap-2 px-1 pt-1">
          <Select value={slug || ROUTE} onValueChange={(v) => onSlug(v === ROUTE ? "" : v)}>
            <SelectTrigger className="h-8 w-auto gap-1 border-0 bg-muted/50 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ROUTE}>Auto-route</SelectItem>
              {pluginSlugs.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              className="size-3.5 accent-primary"
              checked={streaming}
              onChange={(e) => onStreaming(e.target.checked)}
            />
            Stream
          </label>
          <div className="flex-1" />
          <Button size="icon" aria-label="Ask" onClick={onSend} disabled={busy || !value.trim()}>
            {busy ? <Spinner /> : <Send />}
          </Button>
        </div>
      </div>
      <p className="mt-1.5 px-1 text-center text-[11px] text-muted-foreground">
        Enter to send · Shift+Enter for a new line · each question is answered independently
      </p>
    </div>
  );
}
