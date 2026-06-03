// Support tickets list page. Author: Al Amin Ahamed.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listTickets } from "@/api/tickets";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { extractErrorMessage } from "@/lib/queryClient";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export function TicketsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [pluginFilter, setPluginFilter] = useState("all");

  const tickets = useQuery({ queryKey: ["tickets"], queryFn: listTickets });

  const all = tickets.data ?? [];
  const plugins = [...new Set(all.map((t) => t.plugin_slug))].sort();

  const q = search.trim().toLowerCase();
  const filtered = all.filter((t) => {
    const matchQ = !q || t.title.toLowerCase().includes(q) || t.plugin_slug.toLowerCase().includes(q);
    const matchPlugin = pluginFilter === "all" || t.plugin_slug === pluginFilter;
    return matchQ && matchPlugin;
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Support Tickets"
        description="Browse ingested WordPress.org support forum threads."
      />

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard
          icon="ti-ticket"
          label="Total tickets"
          value={tickets.isLoading ? "—" : all.length}
        />
        <StatCard
          icon="ti-puzzle"
          label="Plugins covered"
          value={tickets.isLoading ? "—" : plugins.length}
        />
        <StatCard
          icon="ti-database"
          label="Indexed chunks"
          value={tickets.isLoading ? "—" : all.reduce((s, t) => s + t.chunk_count, 0)}
          tone="success"
        />
      </div>

      {/* Tickets table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3 flex-wrap">
          <CardTitle>Tickets</CardTitle>
          <div className="flex flex-1 items-center gap-2 min-w-0 max-w-lg">
            <div className="relative flex-1">
              <i className="ti ti-search absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground text-[13px]" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by title or plugin…"
                className="pl-7 h-8 text-sm"
              />
            </div>
            <select
              value={pluginFilter}
              onChange={(e) => setPluginFilter(e.target.value)}
              className={cn(
                "h-8 shrink-0 rounded-md border border-input bg-background px-2 text-sm text-foreground",
                "focus:outline-none focus:ring-1 focus:ring-ring",
              )}
            >
              <option value="all">All plugins</option>
              {plugins.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        </CardHeader>
        <CardContent>
          {tickets.isLoading ? (
            <Skeleton className="h-48 w-full" />
          ) : tickets.isError ? (
            <ErrorState message={extractErrorMessage(tickets.error)} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Plugin</TableHead>
                  <TableHead>Creator</TableHead>
                  <TableHead className="text-right">Replies</TableHead>
                  <TableHead className="text-right">Participants</TableHead>
                  <TableHead>Last reply</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={6}
                      className="text-center text-sm text-muted-foreground py-8"
                    >
                      {q || pluginFilter !== "all"
                        ? "No tickets match your filter."
                        : "No support tickets ingested yet."}
                    </TableCell>
                  </TableRow>
                )}
                {filtered.map((t) => (
                  <TableRow
                    key={t.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => void navigate(`/tickets/${t.id}`)}
                  >
                    <TableCell className="max-w-xs">
                      <span className="line-clamp-2 text-sm font-medium">{t.title}</span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="text-[11px]">
                        {t.plugin_slug}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {t.creator ?? <span className="text-xs">—</span>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm text-muted-foreground">
                      {t.reply_count != null ? (
                        <span className="inline-flex items-center gap-1 justify-end">
                          <i className="ti ti-message-2 text-[11px]" />
                          {t.reply_count}
                        </span>
                      ) : (
                        <span className="text-xs">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm text-muted-foreground">
                      {t.participant_count != null ? (
                        <span className="inline-flex items-center gap-1 justify-end">
                          <i className="ti ti-users text-[11px]" />
                          {t.participant_count}
                        </span>
                      ) : (
                        <span className="text-xs">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                      {t.last_reply_at
                        ? relativeTime(t.last_reply_at)
                        : <span className="text-xs">—</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
