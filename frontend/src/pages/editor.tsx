import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { EditorWorkspace } from "@/features/editor/editor-workspace";
import { getProject } from "@/features/projects/api";

export function EditorPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const query = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId!),
    enabled: Boolean(projectId),
  });

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b px-4 py-2">
        <span className="font-semibold">{query.data?.name ?? "Loading…"}</span>
        <Link to="/projects" className="text-sm text-primary hover:underline">
          Back to projects
        </Link>
      </header>
      {projectId && <EditorWorkspace projectId={projectId} />}
    </div>
  );
}
