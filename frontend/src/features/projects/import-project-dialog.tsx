import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";

import { deleteProject } from "./api";
import { useImportProject } from "./use-import-project";
import { PROJECTS_KEY } from "./use-projects";

export function ImportProjectDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const { t } = useTranslation("projects");
  const qc = useQueryClient();
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");

  const { state, start, reset } = useImportProject((projectId) => {
    void qc.invalidateQueries({ queryKey: PROJECTS_KEY });
    toast.success(t("import.success"));
    onOpenChange(false);
    navigate(`/projects/${projectId}`);
  });

  // Reset the form + state machine whenever the dialog opens.
  useEffect(() => {
    if (open) {
      setFile(null);
      setName("");
      reset();
    }
  }, [open, reset]);

  const busy = state.phase === "uploading" || state.phase === "processing";

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!file || busy) return;
    void start(file, name);
  };

  const onDeleteEmpty = async () => {
    if (!state.projectId) return;
    try {
      await deleteProject(state.projectId);
      void qc.invalidateQueries({ queryKey: PROJECTS_KEY });
    } catch {
      // best-effort; the project can still be deleted from the dashboard
    } finally {
      onOpenChange(false);
    }
  };

  const errorText = state.errorType
    ? t([`import.errors.${state.errorType}`, "import.errors.generic"])
    : null;

  return (
    <Dialog open={open} onOpenChange={(v) => (busy ? undefined : onOpenChange(v))}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("import.title")}</DialogTitle>
          <DialogDescription>{t("import.description")}</DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="import-file">{t("import.fileLabel")}</Label>
            <Input
              id="import-file"
              ref={fileInput}
              type="file"
              accept=".zip"
              disabled={busy}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="import-name">{t("import.nameLabel")}</Label>
            <Input
              id="import-name"
              value={name}
              disabled={busy}
              placeholder={t("import.namePlaceholder")}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {state.phase === "uploading" && (
            <div className="space-y-1">
              <Progress
                aria-label={t("import.uploading")}
                aria-valuenow={Math.round(state.progress * 100)}
                value={state.progress * 100}
              />
              <p className="text-sm text-muted-foreground">{t("import.uploading")}</p>
            </div>
          )}

          {state.phase === "processing" && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              {t("import.processing")}
            </p>
          )}

          {state.phase === "failed" && errorText && (
            <div className="space-y-2" role="alert">
              <p className="text-sm text-destructive">{errorText}</p>
              {state.projectId && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void onDeleteEmpty()}
                >
                  {t("import.deleteEmpty")}
                </Button>
              )}
            </div>
          )}

          <DialogFooter>
            <Button type="submit" disabled={!file || busy}>
              {busy ? <Loader2 className="animate-spin" /> : <Upload />}
              {t("import.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
