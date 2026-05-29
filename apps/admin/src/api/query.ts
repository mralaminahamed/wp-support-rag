// Public query + feedback API, incl. SSE streaming. Author: Al Amin Ahamed.
import { getApiBase, getToken } from "@/lib/config";
import type { QueryResponse, SourceRef } from "@/types/api";
import { apiClient } from "./client";

export interface QueryInput {
  question: string;
  plugin_slug?: string | null;
}

export async function postQuery(input: QueryInput): Promise<QueryResponse> {
  const res = await apiClient.post<QueryResponse>("/api/v1/query", input);
  return res.data;
}

export async function postFeedback(
  queryId: string,
  rating: "helpful" | "not_helpful",
): Promise<void> {
  await apiClient.post("/api/v1/feedback", { query_id: queryId, rating });
}

export interface StreamDone {
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

/**
 * Stream an answer via SSE. Calls onToken for each delta and resolves with the
 * final `done` payload. Uses fetch (not axios) for streaming bodies.
 */
export async function streamQuery(
  input: QueryInput,
  onToken: (text: string) => void,
): Promise<StreamDone> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${getApiBase()}/api/v1/query/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(input),
  });
  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        detail = String((body as { detail: unknown }).detail);
      }
    } catch {
      // Non-JSON body; keep the status-based message.
    }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done: StreamDone | null = null;

  for (;;) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = frameField(frame, "event:");
      const data = frameField(frame, "data:");
      if (!data) continue;
      const parsed: unknown = JSON.parse(data);
      if (event === "token") {
        onToken((parsed as { text?: string }).text ?? "");
      } else if (event === "done") {
        done = parsed as StreamDone;
      }
    }
  }
  if (!done) throw new Error("stream ended without a final event");
  return done;
}

function frameField(frame: string, prefix: string): string {
  let value = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith(prefix)) value += line.slice(prefix.length).trim();
  }
  return value;
}
