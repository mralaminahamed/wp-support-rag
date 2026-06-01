// Router. Author: Al Amin Ahamed.
import { createBrowserRouter, Outlet } from "react-router-dom";
import { AuthProvider, RequireAuth } from "@/lib/auth";
import { AppShell } from "@/components/layout/AppShell";
import { AcceptInvitePage } from "@/pages/AcceptInvitePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { LoginPage } from "@/pages/LoginPage";
import { PlaygroundPage } from "@/pages/PlaygroundPage";
import { PluginsPage } from "@/pages/PluginsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { UsersPage } from "@/pages/UsersPage";

function Root() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  );
}

function ProtectedShell() {
  return (
    <RequireAuth>
      <AppShell />
    </RequireAuth>
  );
}

export const router = createBrowserRouter([
  {
    element: <Root />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/accept-invite", element: <AcceptInvitePage /> },
      {
        path: "/",
        element: <ProtectedShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "plugins", element: <PluginsPage /> },
          { path: "playground", element: <PlaygroundPage /> },
          { path: "settings", element: <SettingsPage /> },
          { path: "users", element: <UsersPage /> },
        ],
      },
    ],
  },
]);
