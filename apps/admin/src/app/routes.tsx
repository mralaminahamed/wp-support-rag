// Router. Author: Al Amin Ahamed.
import { createBrowserRouter, Navigate, Outlet } from "react-router-dom";
import { AuthProvider, RequireAuth } from "@/lib/auth";
import { AppShell } from "@/components/layout/AppShell";
import { AcceptInvitePage } from "@/pages/AcceptInvitePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { ForgotPasswordPage } from "@/pages/ForgotPasswordPage";
import { LoginPage } from "@/pages/LoginPage";
import { PlaygroundPage } from "@/pages/PlaygroundPage";
import { PluginsPage } from "@/pages/PluginsPage";
import {
  ProfileOverview,
  ProfilePage,
  ProfilePermissions,
  ProfileSecurity,
} from "@/pages/ProfilePage";
import { ResetPasswordPage } from "@/pages/ResetPasswordPage";
import {
  AdminStep,
  EmbeddingsStep,
  GenerationStep,
  NetworkStep,
  PluginStep,
  SetupWizardLayout,
} from "@/pages/SetupWizardPage";
import { AdaptersPage } from "@/pages/AdaptersPage";
import { TicketDetailPage } from "@/pages/TicketDetailPage";
import { TicketsPage } from "@/pages/TicketsPage";
import { ThreadsListPage } from "@/pages/ThreadsListPage";
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
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
      { path: "/reset-password", element: <ResetPasswordPage /> },
      { path: "/accept-invite", element: <AcceptInvitePage /> },
      {
        path: "/setup",
        element: <SetupWizardLayout />,
        children: [
          { index: true, element: <Navigate to="network" replace /> },
          { path: "network", element: <NetworkStep /> },
          { path: "admin", element: <AdminStep /> },
          { path: "generation", element: <GenerationStep /> },
          { path: "embeddings", element: <EmbeddingsStep /> },
          { path: "plugin", element: <PluginStep /> },
        ],
      },
      {
        path: "/",
        element: <ProtectedShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "plugins", element: <PluginsPage /> },
          {
            path: "playground",
            children: [
              { index: true, element: <PlaygroundPage /> },
              { path: "threads", element: <ThreadsListPage /> },
              { path: "threads/:threadId", element: <PlaygroundPage /> },
            ],
          },
          { path: "users", element: <UsersPage /> },
          { path: "adapters", element: <AdaptersPage /> },
          {
            path: "tickets",
            children: [
              { index: true, element: <TicketsPage /> },
              { path: ":docId", element: <TicketDetailPage /> },
            ],
          },
          {
            path: "profile",
            element: <ProfilePage />,
            children: [
              { index: true, element: <Navigate to="overview" replace /> },
              { path: "overview", element: <ProfileOverview /> },
              { path: "security", element: <ProfileSecurity /> },
              { path: "permissions", element: <ProfilePermissions /> },
            ],
          },
        ],
      },
    ],
  },
]);
