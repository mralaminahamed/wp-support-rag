// Support ticket detail: live replies + reply box. Author: Al Amin Ahamed.
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getTicket } from "@/api/tickets";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/feedback";
import { Skeleton } from "@/components/ui/skeleton";
import { extractErrorMessage } from "@/lib/queryClient";
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

// ── Main page ─────────────────────────────────────────────────────────────────

export function TicketDetailPage() {
  const { docId } = useParams<{ docId: string }>();

  const ticket = useQuery({
    queryKey: ["ticket", docId],
    queryFn: () => getTicket(docId!),
    enabled: !!docId,
  });

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

      {/* Reply on WP.org */}
      <div className="rounded-md border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground flex items-center justify-between gap-3">
        <span>
          <i className="ti ti-info-circle mr-1.5" />
          Replies must be posted directly on WordPress.org (the support forum does not expose a public API for creating replies).
        </span>
        <a
          href={t.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        >
          <i className="ti ti-external-link text-[11px]" />
          Reply on WP.org
        </a>
      </div>
    </div>
  );
}
