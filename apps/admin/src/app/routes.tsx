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
import { EmbeddingSection, GenerationSection, SettingsPage } from "@/pages/SettingsPage";
import { SetupWizardPage } from "@/pages/SetupWizardPage";
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
      { path: "/setup", element: <RequireAuth><SetupWizardPage /></RequireAuth> },
      {
        path: "/",
        element: <ProtectedShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "plugins", element: <PluginsPage /> },
          { path: "playground", element: <PlaygroundPage /> },
          { path: "users", element: <UsersPage /> },
          {
            path: "settings",
            element: <SettingsPage />,
            children: [
              { index: true, element: <Navigate to="generation" replace /> },
              { path: "generation", element: <GenerationSection /> },
              { path: "embeddings", element: <EmbeddingSection /> },
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
