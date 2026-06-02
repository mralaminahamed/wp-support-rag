// AuthContext: provides current user, permission check, and logout.
// On mount calls GET /api/v1/auth/me; redirects to /login on 401.
// Author: Al Amin Ahamed.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getMe, logout as apiLogout } from "@/api/auth";
import { getSetupStatus } from "@/api/admin";
import type { AuthUser } from "@/types/api";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();

  const fetchMe = useCallback(async () => {
    try {
      const me = await getMe();
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchMe();
  }, [fetchMe]);

  const logout = useCallback(async () => {
    await apiLogout().catch(() => {});
    setUser(null);
    navigate("/login", { replace: true });
  }, [navigate]);

  const hasPermission = useCallback(
    (permission: string) => user?.permissions.includes(permission) ?? false,
    [user],
  );

  return (
    <AuthContext.Provider value={{ user, isLoading, logout, hasPermission, refresh: fetchMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  const setupStatus = useQuery({
    queryKey: ["setup-status"],
    queryFn: getSetupStatus,
    enabled: !isLoading && user !== null,
    staleTime: Infinity,
    retry: false,
  });

  // Still loading auth or (auth ok but setup status pending) — render nothing
  if (isLoading || (!isLoading && user !== null && setupStatus.isPending)) return null;

  // Not logged in → login page
  if (user === null) return <Navigate to="/login" replace />;

  // Setup status loaded: enforce the gate (fail open on network error)
  if (setupStatus.data !== undefined) {
    if (!setupStatus.data.complete && location.pathname !== "/setup") {
      return <Navigate to="/setup" replace />;
    }
    if (setupStatus.data.complete && location.pathname === "/setup") {
      return <Navigate to="/" replace />;
    }
  }

  return <>{children}</>;
}
