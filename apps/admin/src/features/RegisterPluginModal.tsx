// Register-plugin form modal. Author: Al Amin Ahamed.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { registerPlugin } from "@/api/admin";
import { useToast } from "@/components/ToastProvider";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { extractErrorMessage } from "@/lib/queryClient";
import { SOURCE_TYPES } from "@/types/api";

export function RegisterPluginModal({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [wporgSlug, setWporgSlug] = useState("");
  const [githubRepo, setGithubRepo] = useState("");
  const [types, setTypes] = useState<string[]>(["wporg_faq", "wporg_changelog"]);

  const mutation = useMutation({
    mutationFn: registerPlugin,
    onSuccess: (data) => {
      toast.ok(`Registered ${data.slug}`);
      void queryClient.invalidateQueries({ queryKey: ["plugins"] });
      onClose();
    },
    onError: (error) => toast.err(extractErrorMessage(error)),
  });

  function toggle(type: string) {
    setTypes((current) =>
      current.includes(type) ? current.filter((t) => t !== type) : [...current, type],
    );
  }

  function submit() {
    if (!slug.trim() || !name.trim()) {
      toast.err("Slug and name are required.");
      return;
    }
    mutation.mutate({
      slug: slug.trim(),
      name: name.trim(),
      wporg_slug: wporgSlug.trim() || null,
      github_repo: githubRepo.trim() || null,
      source_types: types,
    });
  }

  return (
    <Modal
      title="Register plugin"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending ? "Registering…" : "Register"}
          </Button>
        </>
      }
    >
      <Field label="Slug">
        <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="my-plugin" />
      </Field>
      <Field label="Name">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="My Plugin" />
      </Field>
      <Field label="WordPress.org slug" hint="Optional — enables wp.org sources.">
        <Input value={wporgSlug} onChange={(e) => setWporgSlug(e.target.value)} />
      </Field>
      <Field label="GitHub repo" hint="Optional — owner/name.">
        <Input
          value={githubRepo}
          onChange={(e) => setGithubRepo(e.target.value)}
          placeholder="mralaminahamed/my-plugin"
        />
      </Field>
      <p className="mb-1.5 text-[13px] font-medium">Sources</p>
      <div className="grid grid-cols-2 gap-2">
        {SOURCE_TYPES.map((type) => (
          <label key={type} className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              className="h-4 w-4 accent-accent"
              checked={types.includes(type)}
              onChange={() => toggle(type)}
            />
            <span className="font-mono text-[13px]">{type}</span>
          </label>
        ))}
      </div>
    </Modal>
  );
}
