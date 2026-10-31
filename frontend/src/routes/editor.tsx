import { useParams } from "react-router-dom";

import { EditorWorkspace } from "@/modules/editor";

/** The workspace is the whole screen: its tools share the editor's one bar with the title. */
export function EditorRoute() {
  const { projectId } = useParams<{ projectId: string }>();
  return projectId ? <EditorWorkspace projectId={projectId} /> : null;
}
