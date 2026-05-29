// Router: admin shell with Plugins and Metrics pages.
// Author: Al Amin Ahamed.
import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { MetricsPage } from "@/pages/MetricsPage";
import { PluginsPage } from "@/pages/PluginsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <PluginsPage /> },
      { path: "metrics", element: <MetricsPage /> },
    ],
  },
]);
