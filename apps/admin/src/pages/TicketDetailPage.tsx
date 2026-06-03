// Support ticket detail: live replies + reply box. Author: Al Amin Ahamed.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getTicket,
  getWporgCredentials,
  postReply,
  saveWporgCredentials,
} from "@/api/tickets";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ErrorState } from "@/components/ui/feedback";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ToastProvider";
import { extractErrorMessage } from "@/lib/queryClient";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import type { TicketReply } from "@/types/api";

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

// ── Reply card ────────────────────────────────────────────────────────────────

function ReplyCard({ reply }: { reply: TicketReply }) {
  return (
    <div className={cn("flex gap-3", reply.is_topic && "pb-4 border-b border-border")}>
      {/* Avatar */}
      <div className="shrink-0">
        {reply.author_url ? (
          <a href={reply.author_url} target="_blank" rel="noopener noreferrer">
            <Avatar name={reply.author} email="" size={36} />
          </a>
        ) : (
          <Avatar name={reply.author} email="" size={36} />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap mb-1">
          <span className="text-sm font-semibold text-foreground">
            {reply.author_url ? (
              <a
                href={reply.author_url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline"
              >
                {reply.author}
              </a>
            ) : (
              reply.author
            )}
          </span>
          {reply.is_topic && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
              Original poster
            </Badge>
          )}
          <span className="text-[11px] text-muted-foreground ml-auto shrink-0">
            {formatDate(reply.created_at)}
          </span>
        </div>
        <div
          className="prose prose-sm dark:prose-invert max-w-none text-sm [&_p]:my-1.5 [&_pre]:overflow-x-auto [&_code]:text-xs"
          // WP.org returns safe HTML from their own forum, user-generated content
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: reply.content }}
        />
      </div>
    </div>
  );
}

// ── Credentials modal ─────────────────────────────────────────────────────────

function CredentialsModal({
  onClose,
  onSaved,
  currentUsername,
}: {
  onClose: () => void;
  onSaved: () => void;
  currentUsername: string | null;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [username, setUsername] = useState(currentUsername ?? "");
  const [password, setPassword] = useState("");

  const save = useMutation({
    mutationFn: () => saveWporgCredentials(username.trim(), password),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["wporg-credentials"] });
      toast.ok("WP.org credentials saved.");
      onSaved();
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <h2 className="text-lg font-semibold">WordPress.org credentials</h2>
        <p className="text-sm text-muted-foreground">
          Used to post replies to WP.org support threads on your behalf.
          Generate an{" "}
          <a
            href="https://wordpress.org/support/article/application-passwords/"
            target="_blank"
            rel="noopener noreferrer"
            className="underline"
          >
            application password
          </a>{" "}
          at wordpress.org → Profile → Application Passwords.
        </p>
        <Field label="WordPress.org username">
          <Input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="your-username"
          />
        </Field>
        <Field label="Application password">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="xxxx xxxx xxxx xxxx xxxx xxxx"
          />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => save.mutate()}
            disabled={!username.trim() || !password || save.isPending}
          >
            {save.isPending ? "Saving…" : "Save credentials"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function TicketDetailPage() {
  const { docId } = useParams<{ docId: string }>();
  const toast = useToast();
  const qc = useQueryClient();
  const { hasPermission } = useAuth();
  const [replyText, setReplyText] = useState("");
  const [showCredModal, setShowCredModal] = useState(false);

  const ticket = useQuery({
    queryKey: ["ticket", docId],
    queryFn: () => getTicket(docId!),
    enabled: !!docId,
  });

  const creds = useQuery({
    queryKey: ["wporg-credentials"],
    queryFn: getWporgCredentials,
  });

  const reply = useMutation({
    mutationFn: () => postReply(docId!, replyText),
    onSuccess: (data) => {
      toast.ok(data.message);
      setReplyText("");
      void qc.invalidateQueries({ queryKey: ["ticket", docId] });
    },
    onError: (e) => toast.err(extractErrorMessage(e)),
  });

  const canWrite = hasPermission("plugins:write");
  const credConfigured = creds.data?.configured ?? false;

  if (ticket.isLoading) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (ticket.isError || !ticket.data) {
    return (
      <div className="space-y-4">
        <Link to="/tickets" className="text-sm text-muted-foreground hover:underline flex items-center gap-1">
          <i className="ti ti-arrow-left text-[12px]" /> All tickets
        </Link>
        <ErrorState message={ticket.isError ? extractErrorMessage(ticket.error) : "Ticket not found."} />
      </div>
    );
  }

  const t = ticket.data;

  return (
    <div className="space-y-5">
      {/* Back */}
      <Link
        to="/tickets"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground hover:underline"
      >
        <i className="ti ti-arrow-left text-[12px]" /> All tickets
      </Link>

      {/* Header */}
      <div>
        <h2 className="text-[1.05rem] font-bold tracking-tight text-text-1 mb-1">{t.title}</h2>
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="secondary" className="text-[11px]">{t.plugin_slug}</Badge>
          <a
            href={t.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-primary hover:underline inline-flex items-center gap-1"
          >
            View on wordpress.org
            <i className="ti ti-external-link text-[11px]" />
          </a>
        </div>
      </div>

      {/* Live fetch error warning */}
      {t.error && (
        <div className="rounded-md border border-warning/30 bg-warning/5 px-4 py-3 text-sm">
          <span className="font-medium text-warning">
            <i className="ti ti-alert-triangle mr-1.5" />
            Live replies unavailable
          </span>
          <span className="ml-1 text-muted-foreground">{t.error}</span>
        </div>
      )}

      {/* Replies */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>
            Replies
            {t.replies.length > 0 && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({t.replies.length})
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {t.replies.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t.error ? "Could not load replies from WP.org." : "No replies yet."}
            </p>
          ) : (
            <div className="space-y-5">
              {t.replies.map((r) => (
                <ReplyCard key={r.id} reply={r} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Reply box */}
      {canWrite && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Post a reply</CardTitle>
            <button
              type="button"
              onClick={() => setShowCredModal(true)}
              className="text-[11px] text-muted-foreground hover:text-foreground hover:underline inline-flex items-center gap-1"
            >
              <i className="ti ti-settings text-[11px]" />
              {credConfigured
                ? `Posting as ${creds.data?.username}`
                : "Configure credentials"}
            </button>
          </CardHeader>
          <CardContent className="space-y-3">
            {!credConfigured && (
              <div className="rounded-md border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
                <i className="ti ti-lock mr-1.5" />
                WP.org credentials required to post replies.{" "}
                <button
                  type="button"
                  onClick={() => setShowCredModal(true)}
                  className="text-primary hover:underline font-medium"
                >
                  Set up now
                </button>
              </div>
            )}
            <textarea
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              rows={5}
              placeholder="Write your reply…"
              disabled={!credConfigured}
              className={cn(
                "w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
                "placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-y",
                "disabled:opacity-50 disabled:cursor-not-allowed",
              )}
            />
            <div className="flex justify-end">
              <Button
                onClick={() => reply.mutate()}
                disabled={!credConfigured || !replyText.trim() || reply.isPending}
              >
                <i className="ti ti-send mr-1.5 text-[13px]" />
                {reply.isPending ? "Posting…" : "Post reply"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {showCredModal && (
        <CredentialsModal
          currentUsername={creds.data?.username ?? null}
          onClose={() => setShowCredModal(false)}
          onSaved={() => setShowCredModal(false)}
        />
      )}
    </div>
  );
}
