// React Query client with a friendly error extractor.
// Author: Al Amin Ahamed.
import { QueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";

export function extractErrorMessage(error: unknown): string {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (error.response?.status === 401) return "Unauthorized — check the admin token.";
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred";
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (failureCount, error) => {
        if (isAxiosError(error) && error.response?.status === 401) return false;
        return failureCount < 1;
      },
    },
  },
});
