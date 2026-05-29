// Router. Author: Al Amin Ahamed.
import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { DashboardPage } from "@/pages/DashboardPage";
import { PlaygroundPage } from "@/pages/PlaygroundPage";
import { PluginsPage } from "@/pages/PluginsPage";
import { SettingsPage } from "@/pages/SettingsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "plugins", element: <PluginsPage /> },
      { path: "playground", element: <PlaygroundPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);
