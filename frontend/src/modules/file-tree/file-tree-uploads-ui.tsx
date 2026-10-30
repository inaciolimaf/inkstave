import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation("files");
  if (uploads.length === 0) return null;
  return (
    <ul className="space-y-1 border-t p-2" aria-label={t("uploadsLabel")}>
      {uploads.map((u) => (
        <li key={u.key} className="space-y-1 text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate">{u.name}</span>
            <div className="flex items-center gap-1">
              <span className={u.status === "error" ? "text-destructive" : "text-muted-foreground"}>
                {u.status === "error"
                  ? t("uploadStatus.failed")
                  : u.status === "done"
                    ? t("uploadStatus.done")
                    : `${u.pct}%`}
              </span>
              {u.status !== "uploading" && (
                <button
                  type="button"
                  aria-label={t("dismissUpload", { name: u.name })}
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
  const { t } = useTranslation("files");
  return (
    <AlertDialog open={conflict !== null} onOpenChange={(v) => !v && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("conflictDialog.title")}</AlertDialogTitle>
          <AlertDialogDescription>
            {conflict ? t("conflictDialog.description", { name: conflict.file.name }) : null}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("common:action.cancel")}</AlertDialogCancel>
          <AlertDialogAction onClick={onReplace}>{t("conflictDialog.replace")}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
