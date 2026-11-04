import { useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Download, ExternalLink, FileArchive, Globe, Menu } from "lucide-react";
import { useEffect, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button, buttonVariants } from "@/components/ui/button";
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
import { cn } from "@/lib/utils";

import { deleteProject } from "./api";
import { ImportStatus } from "./import-project-dialog";
import { useImportProject } from "./use-import-project";
import { PROJECTS_KEY } from "./use-projects";

/** Where the person browses templates. Inkstave only opens this link; it never fetches it (spec 120). */
export const OVERLEAF_TEMPLATES_URL = "https://www.overleaf.com/latex/templates";

function useOverleafImport(open: boolean, onOpenChange: (v: boolean) => void) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { state, start, reset } = useImportProject(() => {
    void qc.invalidateQueries({ queryKey: PROJECTS_KEY });
  });

  // A new visit starts from an empty drop zone.
  useEffect(() => {
    if (open) reset();
  }, [open, reset]);

  const busy = state.phase === "uploading" || state.phase === "processing";

  const onFile = (file: File) => {
    if (!busy) void start(file, undefined, "overleaf_template");
  };

  const openProject = () => {
    if (!state.projectId) return;
    onOpenChange(false);
    navigate(`/projects/${state.projectId}`);
  };

  const deleteEmpty = async () => {
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

  return { state, busy, onFile, openProject, deleteEmpty };
}

/** A small static diagram of the path to the zip: text is in the step, the icons carry no words. */
function DownloadPath() {
  return (
    <span aria-hidden="true" className="flex flex-wrap items-center gap-1 text-muted-foreground">
      <Globe className="size-4" />
      <ChevronRight className="size-3" />
      <Menu className="size-4" />
      <ChevronRight className="size-3" />
      <Download className="size-4" />
      <ChevronRight className="size-3" />
      <FileArchive className="size-4" />
    </span>
  );
}

function StepNumber({ n }: { n: number }) {
  return (
    <span
      aria-hidden="true"
      className="flex size-6 shrink-0 items-center justify-center rounded-full border text-small font-medium"
    >
      {n}
    </span>
  );
}

/** Drop a .zip here, or choose one. The upload starts as soon as a file is in. */
function DropZone({ disabled, onFile }: { disabled: boolean; onFile: (file: File) => void }) {
  const { t } = useTranslation("projects");
  const [over, setOver] = useState(false);

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setOver(false);
    const file = event.dataTransfer.files[0];
    if (file && !disabled) onFile(file);
  };

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={cn(
        "space-y-2 rounded-md border border-dashed p-4 text-center",
        over && "border-primary bg-accent",
      )}
    >
      <Label htmlFor="overleaf-template-file" className="block cursor-pointer text-body">
        {t("template.dropHint")}
      </Label>
      <Input
        id="overleaf-template-file"
        type="file"
        accept=".zip"
        disabled={disabled}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
    </div>
  );
}

/** The dialog behind "From an Overleaf template…": three steps, then the upload and "Open project". */
export function OverleafTemplateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const { t } = useTranslation("projects");
  const { state, busy, onFile, openProject, deleteEmpty } = useOverleafImport(open, onOpenChange);

  return (
    <Dialog open={open} onOpenChange={(v) => (busy ? undefined : onOpenChange(v))}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("template.title")}</DialogTitle>
          <DialogDescription>{t("template.description")}</DialogDescription>
        </DialogHeader>

        <ol className="space-y-4">
          <li className="flex gap-3">
            <StepNumber n={1} />
            <div className="min-w-0 space-y-2">
              <p className="text-body">{t("template.step1")}</p>
              <a
                href={OVERLEAF_TEMPLATES_URL}
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                {t("template.browse")}
                <ExternalLink aria-hidden="true" className="size-4" />
              </a>
            </div>
          </li>
          <li className="flex gap-3">
            <StepNumber n={2} />
            <div className="min-w-0 space-y-2">
              <p className="text-body">{t("template.step2")}</p>
              <DownloadPath />
            </div>
          </li>
          <li className="flex gap-3">
            <StepNumber n={3} />
            <div className="min-w-0 flex-1 space-y-2">
              <p className="text-body">{t("template.step3")}</p>
              <DropZone disabled={busy} onFile={onFile} />
            </div>
          </li>
        </ol>

        <ImportStatus state={state} onDeleteEmpty={deleteEmpty} />
        {state.phase === "done" && (
          <p className="text-body text-muted-foreground">{t("template.imported")}</p>
        )}

        <DialogFooter>
          {state.phase === "done" && (
            <Button type="button" onClick={openProject}>
              {t("template.openProject")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
