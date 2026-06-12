import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import { UploadError, uploadFile } from "./api";
import { treeKey } from "./use-file-tree";

export interface UploadItem {
  key: string;
  name: string;
  pct: number;
  status: "uploading" | "done" | "error";
  error?: string;
}

/**
 * Owns the file-upload lifecycle: the hidden file input, per-file progress
 * items, and the name-conflict (409) Replace/Cancel prompt (spec 17 §5.3.5).
 */
export function useUploads(projectId: string) {
  const qc = useQueryClient();
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  // A name-conflict (409) upload prompts the user to Replace or Cancel (spec 17 §5.3.5).
  const [conflict, setConflict] = useState<{ file: File; parentId: string | null } | null>(null);

  const uploadInputRef = useRef<HTMLInputElement>(null);
  const uploadParentRef = useRef<string | null>(null);

  // Upload a single file, reporting progress and reconciling the tree. On a
  // name-conflict (409) it returns "conflict" so the caller can prompt the user.
  const runUpload = useCallback(
    async (
      file: File,
      parentId: string | null,
      opts?: { replace?: boolean },
    ): Promise<"ok" | "conflict" | "error"> => {
      const key = `${file.name}-${Math.random().toString(36).slice(2)}`;
      setUploads((u) => [...u, { key, name: file.name, pct: 0, status: "uploading" }]);
      try {
        await uploadFile(projectId, {
          file,
          parentId,
          // Re-issue with a replacement name on overwrite so the new upload wins.
          name: opts?.replace ? file.name : undefined,
          onProgress: (pct) =>
            setUploads((u) => u.map((it) => (it.key === key ? { ...it, pct } : it))),
        });
        setUploads((u) =>
          u.map((it) => (it.key === key ? { ...it, pct: 100, status: "done" } : it)),
        );
        toast.success(`Uploaded ${file.name}`);
        await qc.invalidateQueries({ queryKey: treeKey(projectId) });
        return "ok";
      } catch (err) {
        const code = err instanceof UploadError ? err.code : "upload_failed";
        setUploads((u) =>
          u.map((it) => (it.key === key ? { ...it, status: "error", error: code } : it)),
        );
        toast.error(
          code === "name_conflict"
            ? `“${file.name}” already exists`
            : `Upload of ${file.name} failed`,
        );
        // A first-time name conflict additionally prompts the user to Replace
        // or Cancel (spec 17 §5.3.5); a failed Replace just reports the error.
        return code === "name_conflict" && !opts?.replace ? "conflict" : "error";
      }
    },
    [projectId, qc],
  );

  const onFilesPicked = useCallback(
    async (files: FileList) => {
      const parentId = uploadParentRef.current;
      for (const file of Array.from(files)) {
        const result = await runUpload(file, parentId);
        if (result === "conflict") {
          // Stop the batch and ask the user how to resolve the first conflict.
          setConflict({ file, parentId });
          break;
        }
      }
      if (uploadInputRef.current) uploadInputRef.current.value = "";
    },
    [runUpload],
  );

  const onReplaceConflict = useCallback(async () => {
    if (!conflict) return;
    const { file, parentId } = conflict;
    setConflict(null);
    await runUpload(file, parentId, { replace: true });
  }, [conflict, runUpload]);

  const triggerUpload = useCallback((parentId: string) => {
    uploadParentRef.current = parentId;
    uploadInputRef.current?.click();
  }, []);

  const dismissUpload = useCallback((key: string) => {
    setUploads((list) => list.filter((it) => it.key !== key));
  }, []);

  return {
    uploads,
    conflict,
    setConflict,
    uploadInputRef,
    triggerUpload,
    onFilesPicked,
    onReplaceConflict,
    dismissUpload,
  };
}
