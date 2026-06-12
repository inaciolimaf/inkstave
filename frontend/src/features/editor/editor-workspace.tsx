import { useState } from "react";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { FileTreePanel } from "@/features/file-tree/file-tree-panel";
import type { TreeEntity } from "@/features/file-tree/types";
import { useMediaQuery } from "@/lib/use-media-query";

import { EditorPane } from "./editor-pane";
import { UnsavedChangesGuard } from "./unsaved-changes-guard";

function PreviewPlaceholder() {
  return (
    <div
      className="flex h-full items-center justify-center p-4 text-center text-sm text-muted-foreground"
      aria-label="Preview"
    >
      Preview coming soon.
    </div>
  );
}

export function EditorWorkspace({ projectId }: { projectId: string }) {
  const [selected, setSelected] = useState<TreeEntity | null>(null);
  const [dirty, setDirty] = useState(false);
  const wide = useMediaQuery("(min-width: 768px)");

  return (
    <>
      <ResizablePanelGroup
        direction={wide ? "horizontal" : "vertical"}
        autoSaveId={`inkstave:panes:${projectId}`}
        className="min-h-0 flex-1"
      >
        <ResizablePanel defaultSize={22} minSize={12} className="min-h-0">
          <FileTreePanel
            projectId={projectId}
            selectedId={selected?.id ?? null}
            onSelectEntity={setSelected}
          />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize={48} minSize={20} className="min-h-0">
          <EditorPane
            projectId={projectId}
            selected={selected}
            onClearSelection={() => setSelected(null)}
            onDirtyChange={setDirty}
          />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize={30} minSize={0} className="min-h-0">
          <PreviewPlaceholder />
        </ResizablePanel>
      </ResizablePanelGroup>
      <UnsavedChangesGuard when={dirty} />
    </>
  );
}
