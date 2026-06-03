// Tickets API: list, detail, reply, credentials. Author: Al Amin Ahamed.
import type {
  PostReplyRequest,
  PostReplyResponse,
  TicketDetail,
  TicketSummary,
  WporgCredentials,
} from "@/types/api";
import { apiClient } from "./client";

export async function listTickets(): Promise<TicketSummary[]> {
  const res = await apiClient.get<TicketSummary[]>("/api/v1/admin/tickets");
  return res.data;
}

export async function getTicket(docId: string): Promise<TicketDetail> {
  const res = await apiClient.get<TicketDetail>(`/api/v1/admin/tickets/${docId}`);
  return res.data;
}

export async function postReply(
  docId: string,
  content: string,
): Promise<PostReplyResponse> {
  const res = await apiClient.post<PostReplyResponse>(
    `/api/v1/admin/tickets/${docId}/replies`,
    { content } satisfies PostReplyRequest,
  );
  return res.data;
}

export async function getWporgCredentials(): Promise<WporgCredentials> {
  const res = await apiClient.get<WporgCredentials>("/api/v1/admin/tickets/credentials");
  return res.data;
}

export async function saveWporgCredentials(
  username: string,
  app_password: string,
): Promise<WporgCredentials> {
  const res = await apiClient.put<WporgCredentials>(
    "/api/v1/admin/tickets/credentials",
    { username, app_password },
  );
  return res.data;
}
