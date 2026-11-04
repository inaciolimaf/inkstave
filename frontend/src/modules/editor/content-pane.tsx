import type { ComponentProps, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { EditorPane } from "./editor-pane";
import { FileDrawer } from "./file-drawer";
import type { WorkspaceSearch } from "./workspace-search";

/**
 * The text with its status line (spec 107). The file list opens over it, and the rest is `inert` until it
 * closes. The status line is two hosts: the document's own indicators, and the compile output.
 */
export function ContentPane({
  editor,
  reviewBar,
  filesOpen,
  onOpenFiles,
  onCloseFiles,
  fileTree,
  outline,
  search,
  statusSlotRef,
  outputSlotRef,
}: {
  editor: ComponentProps<typeof EditorPane>;
  /** The bar of an inline review in progress, above the text (spec 110). */
  reviewBar?: ReactNode;
  filesOpen: boolean;
  onOpenFiles: () => void;
  onCloseFiles: () => void;
  fileTree: ReactNode;
  /** The outline, the drawer's second tab (spec 111). */
  outline?: ReactNode;
  /** The project search, the drawer's third tab, which also holds the tab (spec 122). */
  search?: WorkspaceSearch;
  statusSlotRef: (element: HTMLDivElement | null) => void;
  outputSlotRef: (element: HTMLDivElement | null) => void;
}) {
  const { t } = useTranslation("editor");
  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      <div inert={filesOpen} className="flex min-h-0 flex-1 flex-col">
        {reviewBar}
        <div className="min-h-0 flex-1">
          <EditorPane {...editor} />
        </div>
      </div>
      <div className="flex min-h-9 items-center gap-2 border-t pl-2 text-small">
        <div ref={statusSlotRef} className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden" />
        <div ref={outputSlotRef} className="shrink-0" />
      </div>
      <button
        type="button"
        onClick={onOpenFiles}
        className="absolute left-0 top-1/2 z-10 hidden -translate-y-1/2 rounded-r border border-l-0 border-control-edge bg-muted px-1 py-3 text-small font-medium text-muted-foreground [writing-mode:vertical-rl] hover:bg-accent hover:text-foreground md:block"
      >
        {t("toolbar.files")}
      </button>
      <FileDrawer
        open={filesOpen}
        onClose={onCloseFiles}
        outline={outline}
        search={search?.panel}
        tab={search?.tab}
        onTabChange={search?.setTab}
      >
        {fileTree}
      </FileDrawer>
    </div>
  );
}
