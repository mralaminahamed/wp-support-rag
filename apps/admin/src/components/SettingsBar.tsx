// Connection settings: API base URL + admin bearer token (persisted locally).
// Author: Al Amin Ahamed.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getApiBase, getToken, setApiBase, setToken } from "@/lib/config";

export function SettingsBar() {
  const queryClient = useQueryClient();
  const [api, setApi] = useState(getApiBase());
  const [token, setTok] = useState(getToken());

  function apply() {
    setApiBase(api.trim());
    setToken(token.trim());
    void queryClient.invalidateQueries();
  }

  return (
    <div className="topbar">
      <h1>WP Support RAG — Admin</h1>
      <input
        id="api"
        value={api}
        onChange={(e) => setApi(e.target.value)}
        placeholder="API base URL"
      />
      <input
        id="token"
        type="password"
        value={token}
        onChange={(e) => setTok(e.target.value)}
        placeholder="Admin bearer token"
      />
      <button onClick={apply}>Connect</button>
    </div>
  );
}
