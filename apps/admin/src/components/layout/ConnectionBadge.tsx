// Live API health badge. Author: Al Amin Ahamed.
import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/api/admin";
import { Badge } from "@/components/ui/badge";

export function ConnectionBadge() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 15_000,
    retry: false,
  });

  if (health.isLoading) return <Badge variant="secondary">checking…</Badge>;
  if (health.isError) return <Badge variant="destructive">API unreachable</Badge>;

  const ok = health.data?.status === "ok";
  return <Badge variant={ok ? "success" : "warning"}>{ok ? "healthy" : "degraded"}</Badge>;
}
