import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { InkstaveMark } from "@/components/inkstave-logo";
import { Desk } from "@/components/manuscript";
import { EditorWorkspace } from "@/modules/editor";
import { getProject, projectKey } from "@/modules/projects";

export function EditorRoute() {
  const { t } = useTranslation(["editor", "common"]);
  const { projectId } = useParams<{ projectId: string }>();
  const query = useQuery({
    queryKey: projectKey(projectId),
    queryFn: () => getProject(projectId!),
    enabled: Boolean(projectId),
  });

  return (
    <Desk
      bar={
        <header className="flex items-center justify-between gap-4 border-b px-4 py-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <Link to="/projects" aria-label="Inkstave" className="shrink-0 hover:opacity-80">
              <InkstaveMark className="h-5 w-5 text-foreground" />
            </Link>
            <h1 className="truncate font-serif text-heading font-medium">
              {query.data?.name ?? t("common:state.loading")}
            </h1>
          </div>
          <Link to="/projects" className="shrink-0 text-body text-muted-foreground hover:text-foreground">
            {t("toolbar.backToProjects")}
          </Link>
        </header>
      }
    >
      {projectId && <EditorWorkspace projectId={projectId} />}
    </Desk>
  );
}
