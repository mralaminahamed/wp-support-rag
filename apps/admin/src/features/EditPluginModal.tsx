// Edit-plugin dialog. Author: Al Amin Ahamed.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { updatePlugin } from "@/api/admin";
import { useToast } from "@/components/ToastProvider";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { extractErrorMessage } from "@/lib/queryClient";
import type { PluginSummary } from "@/types/api";

export function EditPluginModal({
  plugin,
  onClose,
}: {
  plugin: PluginSummary;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState(plugin.name);
  const [wporgSlug, setWporgSlug] = useState(plugin.wporg_slug ?? "");
  const [githubRepo, setGithubRepo] = useState(plugin.github_repo ?? "");
  const [status, setStatus] = useState<"active" | "paused">(
    plugin.status === "paused" ? "paused" : "active",
  );

  useEffect(() => {
    setName(plugin.name);
    setWporgSlug(plugin.wporg_slug ?? "");
    setGithubRepo(plugin.github_repo ?? "");
    setStatus(plugin.status === "paused" ? "paused" : "active");
  }, [plugin]);

  const mutation = useMutation({
    mutationFn: () =>
      updatePlugin(plugin.slug, {
        name: name.trim(),
        wporg_slug: wporgSlug.trim() || null,
        github_repo: githubRepo.trim() || null,
        status,
      }),
    onSuccess: () => {
      toast.ok(`Updated ${plugin.slug}`);
      void queryClient.invalidateQueries({ queryKey: ["plugins"] });
      onClose();
    },
    onError: (error) => toast.err(extractErrorMessage(error)),
  });

  function submit() {
    if (!name.trim()) {
      toast.err("Name is required.");
      return;
    }
    mutation.mutate();
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit plugin</DialogTitle>
          <DialogDescription>
            Update metadata for <span className="font-mono">{plugin.slug}</span>.
          </DialogDescription>
        </DialogHeader>

        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="My Plugin" />
        </Field>
        <Field label="WordPress.org slug" hint="Optional — leave blank to clear.">
          <Input value={wporgSlug} onChange={(e) => setWporgSlug(e.target.value)} />
        </Field>
        <Field label="GitHub repo" hint="Optional — owner/name. Leave blank to clear.">
          <Input
            value={githubRepo}
            onChange={(e) => setGithubRepo(e.target.value)}
            placeholder="mralaminahamed/my-plugin"
          />
        </Field>
        <Field label="Status">
          <div className="flex gap-4">
            {(["active", "paused"] as const).map((s) => (
              <label key={s} className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="radio"
                  className="accent-primary"
                  checked={status === s}
                  onChange={() => setStatus(s)}
                />
                <span className="capitalize">{s}</span>
              </label>
            ))}
          </div>
        </Field>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
