import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { InkstaveMark } from "@/components/inkstave-logo";
import { EditorWorkspace } from "@/features/editor/editor-workspace";
import { getProject } from "@/features/projects/api";

export function EditorPage() {
  const { t } = useTranslation(["editor", "common"]);
  const { projectId } = useParams<{ projectId: string }>();
  const query = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId!),
    enabled: Boolean(projectId),
  });

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between gap-4 border-b px-4 py-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <Link to="/projects" aria-label="Inkstave" className="shrink-0 hover:opacity-80">
            <InkstaveMark className="h-5 w-5 text-foreground" />
          </Link>
          <span className="truncate font-semibold">
            {query.data?.name ?? t("common:state.loading")}
          </span>
        </div>
        <Link to="/projects" className="shrink-0 text-sm text-primary hover:underline">
          {t("toolbar.backToProjects")}
        </Link>
      </header>
      {projectId && <EditorWorkspace projectId={projectId} />}
    </div>
  );
}
