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

  if (health.isLoading) return <Badge tone="neutral">checking…</Badge>;
  if (health.isError) return <Badge tone="err" dot>API unreachable</Badge>;

  const ok = health.data?.status === "ok";
  return (
    <Badge tone={ok ? "ok" : "warn"} dot>
      {ok ? "healthy" : "degraded"}
    </Badge>
  );
}
