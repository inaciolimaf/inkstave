/** The editor bar as the workspace wires it: the Insert menu, the chat button and the dialogs it opens. */
import type { EditorView } from "@codemirror/view";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { InsertMenu } from "@/modules/insert-tools";
import { getProject, projectKey } from "@/modules/projects";

import { EditorBar } from "./editor-bar";
import { useMainDocumentText } from "./use-main-document-text";
import type { useSourceSync } from "./use-source-sync";
import type { useWorkspaceDialogs } from "./workspace-hooks";

/** The Insert menu, with the main document's text for the packages it loads (spec 114). */
function WorkspaceInsert({
  projectId,
  view,
  readOnly,
}: {
  projectId: string;
  view: EditorView | null;
  readOnly: boolean;
}) {
  const project = useQuery({ queryKey: projectKey(projectId), queryFn: () => getProject(projectId) });
  const mainText = useMainDocumentText(projectId, project.data?.rootDocId);
  return <InsertMenu view={view} readOnly={readOnly} mainText={mainText} />;
}

export function WorkspaceBar({
  projectId,
  projectName,
  sync,
  compileSlotRef,
  readOnly,
  chatButton,
  dialogs,
  onOpenFiles,
}: {
  projectId: string;
  projectName: string | undefined;
  sync: ReturnType<typeof useSourceSync>;
  compileSlotRef: (el: HTMLElement | null) => void;
  readOnly: boolean;
  chatButton: ReactNode;
  dialogs: ReturnType<typeof useWorkspaceDialogs>;
  onOpenFiles: () => void;
}) {
  return (
    <EditorBar
      projectId={projectId}
      projectName={projectName}
      fileName={sync.openDoc?.name}
      onOpenFiles={onOpenFiles}
      compileSlotRef={compileSlotRef}
      historyDisabled={sync.openDoc?.type !== "doc"}
      onOpenHistory={() => dialogs.setHistoryOpen(true)}
      onOpenShare={() => dialogs.setShareOpen(true)}
      insert={<WorkspaceInsert projectId={projectId} view={sync.editorView} readOnly={readOnly} />}
      chatButton={chatButton}
    />
  );
}
