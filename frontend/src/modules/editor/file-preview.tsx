/** A project file that is not a text document: a PDF or an image is shown, anything else explained. */
import { FileText } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import type { TreeEntity } from "@/modules/file-tree";
import { getProjectFileBytes, ProjectFilePdf } from "@/modules/pdf-preview";

import { fileKind, IMAGE_TYPES } from "./file-kind";

function BinaryNotice() {
  const { t } = useTranslation("editor");
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-body text-muted-foreground">
      <FileText className="size-8" />
      <p>{t("pane.binaryFile")}</p>
    </div>
  );
}

/** An object URL for the file's bytes, revoked when the file changes or the pane closes. */
function useFileObjectUrl(projectId: string, entity: TreeEntity): { url: string | null; failed: boolean } {
  const [state, setState] = useState<{ url: string | null; failed: boolean }>({ url: null, failed: false });
  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    setState({ url: null, failed: false });
    const type = IMAGE_TYPES[entity.name.split(".").pop()?.toLowerCase() ?? ""];
    getProjectFileBytes(projectId, entity.id)
      .then((bytes) => {
        if (cancelled) return;
        url = URL.createObjectURL(new Blob([bytes], { type }));
        setState({ url, failed: false });
      })
      .catch(() => {
        if (!cancelled) setState({ url: null, failed: true });
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [projectId, entity.id, entity.name]);
  return state;
}

function ImagePreview({ projectId, entity }: { projectId: string; entity: TreeEntity }) {
  const { t } = useTranslation("editor");
  const { url, failed } = useFileObjectUrl(projectId, entity);
  if (failed) return <BinaryNotice />;
  if (!url) return <Skeleton className="m-4 h-full" aria-busy="true" />;
  return (
    <div className="flex h-full items-center justify-center overflow-auto p-4">
      <img src={url} alt={t("pane.imagePreview", { name: entity.name })} className="max-h-full max-w-full" />
    </div>
  );
}

export function FilePreview({ projectId, entity }: { projectId: string; entity: TreeEntity }) {
  const kind = fileKind(entity.name);
  if (kind === "pdf") return <ProjectFilePdf key={entity.id} projectId={projectId} entityId={entity.id} />;
  if (kind === "image") return <ImagePreview projectId={projectId} entity={entity} />;
  return <BinaryNotice />;
}
