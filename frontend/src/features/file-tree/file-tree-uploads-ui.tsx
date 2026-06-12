import { X } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Progress } from "@/components/ui/progress";

import type { UploadItem } from "./use-uploads";

/** The per-file upload progress list shown at the bottom of the panel. */
export function UploadList({
  uploads,
  onDismiss,
}: {
  uploads: UploadItem[];
  onDismiss: (key: string) => void;
}) {
  if (uploads.length === 0) return null;
  return (
    <ul className="space-y-1 border-t p-2" aria-label="Uploads">
      {uploads.map((u) => (
        <li key={u.key} className="space-y-1 text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate">{u.name}</span>
            <div className="flex items-center gap-1">
              <span className={u.status === "error" ? "text-destructive" : "text-muted-foreground"}>
                {u.status === "error" ? "Failed" : u.status === "done" ? "Done" : `${u.pct}%`}
              </span>
              {u.status !== "uploading" && (
                <button
                  type="button"
                  aria-label={`Dismiss ${u.name}`}
                  onClick={() => onDismiss(u.key)}
                >
                  <X className="size-3" />
                </button>
              )}
            </div>
          </div>
          {u.status === "uploading" && <Progress value={u.pct} />}
        </li>
      ))}
    </ul>
  );
}

/** Replace/Cancel prompt shown on an upload name-conflict (spec 17 §5.3.5). */
export function UploadConflictDialog({
  conflict,
  onCancel,
  onReplace,
}: {
  conflict: { file: File } | null;
  onCancel: () => void;
  onReplace: () => void;
}) {
  return (
    <AlertDialog open={conflict !== null} onOpenChange={(v) => !v && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>File already exists</AlertDialogTitle>
          <AlertDialogDescription>
            {conflict
              ? `“${conflict.file.name}” already exists in this folder. Replace it with the uploaded file?`
              : null}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onReplace}>Replace</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
