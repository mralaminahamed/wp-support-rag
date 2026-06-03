// Threads list: all conversation threads with links to the playground.
// Author: Al Amin Ahamed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { deleteThread, listThreads } from "@/api/admin";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ThreadSummary } from "@/types/api";

function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function ThreadRow({ thread, onDelete }: { thread: ThreadSummary; onDelete: () => void }) {
  const [confirming, setConfirming] = useState(false);

  return (
    <li className="group flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors">
      <Link
        to={`/playground/threads/${thread.id}`}
        className="flex-1 min-w-0 flex items-center gap-3"
      >
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <i className="ti ti-message-chatbot text-sm text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="truncate text-sm font-medium leading-tight">{thread.title}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {thread.owner_email && (
              <span className="font-mono mr-2 text-muted-foreground/70">{thread.owner_email}</span>
            )}
            {thread.plugin_slug && (
              <span className="font-mono mr-2 text-primary/70">{thread.plugin_slug}</span>
            )}
            {relativeTime(thread.updated_at)}
          </p>
        </div>
      </Link>

      <div className="shrink-0 flex items-center gap-1">
        {confirming ? (
          <>
            <button
              className="text-xs text-destructive hover:underline px-1"
              onClick={() => { onDelete(); setConfirming(false); }}
            >
              Delete
            </button>
            <button
              className="text-xs text-muted-foreground hover:underline px-1"
              onClick={() => setConfirming(false)}
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded text-muted-foreground hover:text-destructive"
            onClick={() => setConfirming(true)}
            aria-label="Delete thread"
          >
            <i className="ti ti-trash text-sm" />
          </button>
        )}
      </div>
    </li>
  );
}

export function ThreadsListPage() {
  const qc = useQueryClient();
  const threads = useQuery({ queryKey: ["threads"], queryFn: listThreads });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteThread(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["threads"] }),
  });

  const list = threads.data ?? [];

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Threads</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Past conversations in the playground.
          </p>
        </div>
        <Button asChild size="sm">
          <Link to="/playground">
            <i className="ti ti-plus mr-1.5 text-sm" /> New chat
          </Link>
        </Button>
      </div>

      {threads.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-muted">
            <i className="ti ti-history text-2xl text-muted-foreground" />
          </div>
          <p className="mt-4 text-sm font-medium">No threads yet</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Start a conversation in the playground.
          </p>
          <Button asChild variant="outline" size="sm" className="mt-4">
            <Link to="/playground">Open playground</Link>
          </Button>
        </div>
      ) : (
        <ul className="space-y-0.5">
          {list.map((t) => (
            <ThreadRow
              key={t.id}
              thread={t}
              onDelete={() => deleteMutation.mutate(t.id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
