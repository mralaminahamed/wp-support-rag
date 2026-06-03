// Playground: threaded chat-style grounded Q&A. Author: Al Amin Ahamed.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  appendMessages,
  createThread,
  getThreadMessages,
  listPlugins,
} from "@/api/admin";
import { postFeedback, postQuery, streamQuery } from "@/api/query";
import { Logo } from "@/components/Logo";
import { useToast } from "@/components/ToastProvider";
import { Avatar } from "@/components/ui/avatar";
import { useAuth } from "@/lib/auth";
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
import type { QueryResponse, SourceRef, ThreadMessage } from "@/types/api";

function uuidv4(): string {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  b.set([(b[6]! & 0x0f) | 0x40], 6);
  b.set([(b[8]! & 0x3f) | 0x80], 8);
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

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

interface Turn {
  id: string;
  question: string;
  live: string;
  result: QueryResponse | null;
  error: string | null;
  feedbackSent: boolean;
}

function messagestoTurns(msgs: ThreadMessage[]): Turn[] {
  const turns: Turn[] = [];
  for (let i = 0; i < msgs.length; i += 2) {
    const user = msgs[i];
    const asst = msgs[i + 1];
    if (!user || user.role !== "user") break;
    const result: QueryResponse | null =
      asst?.role === "assistant" && asst.meta
        ? (asst.meta as unknown as QueryResponse)
        : asst?.role === "assistant"
          ? {
              query_id: asst.query_id ?? user.id,
              answer: asst.content,
              citations: [],
              sources: [],
              cached: false,
              degraded: false,
              declined: false,
              plugin_slug: null,
              latency_ms: 0,
              provider: "",
              model: "",
            }
          : null;
    turns.push({
      id: user.id,
      question: user.content,
      live: "",
      result,
      error: null,
      feedbackSent: false,
    });
  }
  return turns;
}

export function PlaygroundPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { threadId: urlThreadId } = useParams<{ threadId?: string }>();
  const currentThreadId = urlThreadId ?? null;

  const plugins = useQuery({ queryKey: ["plugins"], queryFn: listPlugins });

  const [messages, setMessages] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [slug, setSlug] = useState("");
  const [streaming, setStreaming] = useState(
    () => localStorage.getItem("playground-streaming") !== "false",
  );
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const prevLengthRef = useRef(0);
  // Prevents the thread-load effect from wiping messages when a thread is
  // auto-created during an active run() call.
  const suppressNextReloadRef = useRef(false);

  // Smooth scroll on new message; instant during streaming.
  useEffect(() => {
    const isNew = messages.length > prevLengthRef.current;
    prevLengthRef.current = messages.length;
    bottomRef.current?.scrollIntoView({ behavior: isNew ? "smooth" : "auto", block: "end" });
  }, [messages]);

  // Load messages when the user selects a thread from the sidebar.
  // Suppressed when a thread is auto-created mid-run to avoid wiping live messages.
  useEffect(() => {
    if (!currentThreadId) {
      setMessages([]);
      return;
    }
    if (suppressNextReloadRef.current) {
      suppressNextReloadRef.current = false;
      return;
    }
    void getThreadMessages(currentThreadId).then((msgs) => {
      setMessages(messagestoTurns(msgs));
    });
  }, [currentThreadId]);

  function patch(id: string, change: Partial<Turn>) {
    setMessages((m) => m.map((t) => (t.id === id ? { ...t, ...change } : t)));
  }

  function handleSetStreaming(v: boolean) {
    localStorage.setItem("playground-streaming", String(v));
    setStreaming(v);
  }

  async function ensureThread(question: string): Promise<string> {
    if (currentThreadId) return currentThreadId;
    const title = question.slice(0, 80);
    const t = await createThread(title, slug || null);
    void qc.invalidateQueries({ queryKey: ["threads"] });
    suppressNextReloadRef.current = true;
    void navigate(`/playground/threads/${t.id}`, { replace: true });
    return t.id;
  }

  async function run(override?: string) {
    const q = (override ?? input).trim();
    if (!q || busy) return;
    setInput("");
    const id = uuidv4();
    setMessages((m) => [
      ...m,
      { id, question: q, live: "", result: null, error: null, feedbackSent: false },
    ]);
    setBusy(true);
    const reqInput = { question: q, plugin_slug: slug || null };
    let threadId: string | null = null;
    try {
      threadId = await ensureThread(q);
      let finalResult: QueryResponse;
      if (streaming) {
        const done = await streamQuery(reqInput, (t) =>
          setMessages((m) => m.map((x) => (x.id === id ? { ...x, live: x.live + t } : x))),
        );
        finalResult = done as QueryResponse;
        patch(id, { result: finalResult, live: "" });
      } else {
        finalResult = await postQuery(reqInput);
        patch(id, { result: finalResult });
      }
      // Persist both messages to the thread.
      await appendMessages(threadId, [
        { role: "user", content: q },
        {
          role: "assistant",
          content: finalResult.answer,
          query_id: finalResult.query_id,
          meta: finalResult as unknown as Record<string, unknown>,
        },
      ]);
      void qc.invalidateQueries({ queryKey: ["threads"] });
    } catch (error) {
      patch(id, { error: extractErrorMessage(error) });
      // Still persist user turn with error marker if we have a thread.
      if (threadId) {
        await appendMessages(threadId, [
          { role: "user", content: q },
          { role: "assistant", content: `[Error] ${extractErrorMessage(error)}` },
        ]).catch(() => undefined);
      }
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

  function startNewChat() {
    setMessages([]);
    setInput("");
    void navigate("/playground");
  }

  return (
    <div className="flex h-[calc(100dvh-7rem)] flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b px-4 py-2 shrink-0">
        <Button variant="outline" size="sm" className="gap-2 text-xs" onClick={startNewChat}>
          <i className="ti ti-plus text-sm" /> New chat
        </Button>
        <Link
          to="/playground/threads"
          className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <i className="ti ti-history text-sm" /> Threads
        </Link>
      </div>

      {/* Conversation area */}
      <div className="flex-1 overflow-y-auto px-4">
        {messages.length === 0 ? (
          <Greeting onPick={(q) => void run(q)} disabled={busy} />
        ) : (
          <div className="mx-auto max-w-3xl space-y-6 py-4">
            {messages.map((turn) => (
              <div key={turn.id} className="space-y-4">
                <UserBubble text={turn.question} />
                <AssistantMessage
                  turn={turn}
                  onFeedback={sendFeedback}
                  onCopy={(text) => {
                    void navigator.clipboard?.writeText(text).then(() => toast.ok("Copied!"));
                  }}
                />
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="mx-auto w-full max-w-3xl px-4">
        <Composer
          value={input}
          onChange={setInput}
          onSend={() => void run()}
          busy={busy}
          slug={slug}
          onSlug={setSlug}
          streaming={streaming}
          onStreaming={handleSetStreaming}
          pluginSlugs={plugins.data?.map((p) => p.slug) ?? []}
        />
      </div>
    </div>
  );
}

function Greeting({ onPick, disabled }: { onPick: (q: string) => void; disabled: boolean }) {
  return (
    <div className="flex h-full flex-col items-center justify-center py-12 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10">
        <i className="ti ti-sparkles text-2xl text-primary" />
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
  const { user } = useAuth();
  const email = user?.email ?? "";
  const name = email.split("@")[0] ?? "User";
  return (
    <div className="flex justify-end gap-3">
      <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
        {text}
      </div>
      <Avatar name={name} email={email} size={32} />
    </div>
  );
}

function AssistantMessage({
  turn,
  onFeedback,
  onCopy,
}: {
  turn: Turn;
  onFeedback: (turn: Turn, rating: "helpful" | "not_helpful") => void;
  onCopy: (text: string) => void;
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
            <i className="ti ti-alert-triangle text-base shrink-0" /> {error}
          </p>
        ) : result ? (
          <>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              {result.declined && <Badge variant="warning">declined</Badge>}
              {result.degraded && <Badge variant="warning">degraded</Badge>}
              {result.cached && <Badge variant="accent">cached</Badge>}
              {result.provider && (
                <Badge variant="secondary">
                  {result.provider} · {result.model}
                </Badge>
              )}
              {result.latency_ms > 0 && (
                <Badge variant="secondary">{result.latency_ms} ms</Badge>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto"
                onClick={() => onCopy(result.answer)}
              >
                <i className="ti ti-copy text-sm" /> Copy
              </Button>
            </div>

            <Markdown>{result.answer}</Markdown>

            {result.sources.length > 0 && <SourceList sources={result.sources} />}

            {!result.declined && (
              <div className="mt-3 flex items-center gap-2 border-t pt-3 text-sm text-muted-foreground">
                <span>Was this helpful?</span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Helpful"
                  disabled={turn.feedbackSent}
                  onClick={() => onFeedback(turn, "helpful")}
                >
                  <i className="ti ti-thumb-up text-sm" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Not helpful"
                  disabled={turn.feedbackSent}
                  onClick={() => onFeedback(turn, "not_helpful")}
                >
                  <i className="ti ti-thumb-down text-sm" />
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

function SourceList({ sources }: { sources: SourceRef[] }) {
  return (
    <div className="mt-4">
      <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        Sources · {sources.filter((s) => s.cited).length} cited
      </p>
      <ol className="space-y-1.5">
        {sources.map((s, i) => (
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
                  <i className="ti ti-check text-xs" /> cited
                </span>
              )}
              <span className="ml-auto truncate font-mono text-xs text-muted-foreground">
                {hostOf(s.url)}
              </span>
              <i className="ti ti-external-link text-sm shrink-0 text-muted-foreground" />
            </a>
          </li>
        ))}
      </ol>
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
            {busy ? <Spinner /> : <i className="ti ti-send text-sm" />}
          </Button>
        </div>
      </div>
      <p className="mt-1.5 px-1 text-center text-[11px] text-muted-foreground">
        Enter to send · Shift+Enter for a new line · each question is answered independently
      </p>
    </div>
  );
}
