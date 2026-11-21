/** A PDF from the project's files, shown in the editor pane with the preview's viewer and toolbar. */
import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";

import { PdfToolbar } from "./PdfToolbar";
import { PdfViewer } from "./PdfViewer";
import { useProjectFilePdf } from "./hooks/usePdfDocument";
import { usePdfViewport } from "./hooks/usePdfViewport";

export function ProjectFilePdf({ projectId, entityId }: { projectId: string; entityId: string }) {
  const { t } = useTranslation("preview");
  const doc = useProjectFilePdf(projectId, entityId);
  const viewport = usePdfViewport(doc.numPages);
  if (doc.error) {
    return (
      <p role="alert" className="flex h-full items-center justify-center p-6 text-body text-muted-foreground">
        {t("errors.loadPdf")}
      </p>
    );
  }
  if (!doc.pdf) return <Skeleton className="m-4 h-full" aria-busy="true" />;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-border px-2 py-1">
        <PdfToolbar viewport={viewport} />
      </div>
      <div className="min-h-0 flex-1">
        <PdfViewer pdf={doc.pdf} viewport={viewport} />
      </div>
    </div>
  );
}
