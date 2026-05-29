// Plugins page: list registered plugins, trigger ingestion per plugin or all.
// Author: Al Amin Ahamed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ingestAll, ingestPlugin, listPlugins } from "@/api/admin";
import { extractErrorMessage } from "@/lib/queryClient";

export function PluginsPage() {
  const queryClient = useQueryClient();
  const plugins = useQuery({ queryKey: ["plugins"], queryFn: listPlugins });

  const ingestOne = useMutation({
    mutationFn: ingestPlugin,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["plugins"] }),
  });
  const ingestEverything = useMutation({ mutationFn: ingestAll });

  if (plugins.isLoading) return <p className="muted">Loading plugins…</p>;
  if (plugins.isError)
    return <p className="err">{extractErrorMessage(plugins.error)}</p>;

  const rows = plugins.data ?? [];
  return (
    <section>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <strong>{rows.length} plugins</strong>
        <button
          className="secondary"
          disabled={ingestEverything.isPending}
          onClick={() => ingestEverything.mutate()}
        >
          {ingestEverything.isPending ? "Enqueuing…" : "Ingest all"}
        </button>
        {ingestEverything.isSuccess && (
          <span className="muted">
            Enqueued {ingestEverything.data.enqueued_sources} sources across{" "}
            {ingestEverything.data.plugins} plugins.
          </span>
        )}
        {ingestEverything.isError && (
          <span className="err">{extractErrorMessage(ingestEverything.error)}</span>
        )}
      </div>

      <table>
        <thead>
          <tr>
            <th>Slug</th>
            <th>Name</th>
            <th>Sources</th>
            <th>GitHub</th>
            <th>wp.org</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.slug}>
              <td>{p.slug}</td>
              <td>{p.name}</td>
              <td>{p.source_count}</td>
              <td>{p.github_repo ?? "—"}</td>
              <td>{p.wporg_slug ?? "—"}</td>
              <td>
                <button
                  disabled={ingestOne.isPending}
                  onClick={() => ingestOne.mutate(p.slug)}
                >
                  Ingest
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
