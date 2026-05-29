// App layout: settings bar, tabs, and the routed page outlet.
// Author: Al Amin Ahamed.
import { NavLink, Outlet } from "react-router-dom";
import { SettingsBar } from "./SettingsBar";

export function AppShell() {
  return (
    <div className="shell">
      <SettingsBar />
      <nav className="tabs">
        <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
          Plugins
        </NavLink>
        <NavLink to="/metrics" className={({ isActive }) => (isActive ? "active" : "")}>
          Metrics
        </NavLink>
      </nav>
      <Outlet />
    </div>
  );
}
