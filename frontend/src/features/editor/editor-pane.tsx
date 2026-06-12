import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import type { TreeEntity } from "@/features/file-tree/types";

import { getDocument } from "./api";
import { useDocumentAutosave } from "./autosave/use-document-autosave";
import { CodeMirrorEditor } from "./codemirror-editor";
import { ConflictDialog } from "./conflict-dialog";
import { EditorSettingsPopover } from "./editor-settings-popover";
import { SaveStatusIndicator } from "./save-status-indicator";
import { documentKey } from "./use-document";
import { useEditorSettings } from "./use-editor-settings";
import { useIsDark } from "./use-is-dark";

function EmptyState() {
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
      Select a file to start editing.
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-2 p-4" aria-busy="true" aria-label="Loading document">
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-4" style={{ width: `${90 - (i % 4) * 12}%` }} />
      ))}
    </div>
  );
}

function ErrorState({ onRetry, notFound }: { onRetry: () => void; notFound: boolean }) {
  return (
    <div role="alert" className="flex h-full flex-col items-center justify-center gap-3 text-sm">
      <p className="text-destructive">
        {notFound ? "This document no longer exists." : "Couldn’t load this document."}
      </p>
      {!notFound && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

function BinaryNotice() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
      <FileText className="size-8" />
      <p>This is a binary file and can’t be edited here.</p>
    </div>
  );
}

export function EditorPane({
  projectId,
  selected,
  onClearSelection,
  onDirtyChange,
}: {
  projectId: string;
  selected: TreeEntity | null;
  onClearSelection: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { settings, update } = useEditorSettings();
  const dark = useIsDark();

  // Folders are ignored: keep the last opened doc/file as the active entity.
  const [openEntity, setOpenEntity] = useState<TreeEntity | null>(null);
  useEffect(() => {
    if (selected && selected.type !== "folder") setOpenEntity(selected);
  }, [selected]);

  const docId = openEntity?.type === "doc" ? openEntity.id : null;
  const query = useQuery({
    queryKey: documentKey(projectId, docId ?? ""),
    queryFn: () => getDocument(projectId, docId!),
    enabled: Boolean(docId),
    placeholderData: keepPreviousData,
  });

  const isDoc = openEntity?.type === "doc";
  const loaded = isDoc && query.data ? query.data : null;
  const {
    status,
    displayText,
    hasUnsaved,
    conflict,
    onLocalChange,
    saveNow,
    resolveReload,
    resolveKeepMine,
  } = useDocumentAutosave(projectId, loaded);

  const notFound = query.error instanceof ApiError && query.error.status === 404;
  useEffect(() => {
    if (notFound) {
      setOpenEntity(null);
      onClearSelection();
    }
  }, [notFound, onClearSelection]);

  useEffect(() => {
    onDirtyChange?.(hasUnsaved);
  }, [hasUnsaved, onDirtyChange]);

  // Ctrl/Cmd+S forces an immediate flush and suppresses the browser save dialog.
  useEffect(() => {
    if (!isDoc) return;
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        saveNow();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isDoc, saveNow]);

  let body: React.ReactNode;
  if (!openEntity) body = <EmptyState />;
  else if (openEntity.type === "file") body = <BinaryNotice />;
  else if (query.isError)
    body = <ErrorState onRetry={() => void query.refetch()} notFound={notFound} />;
  else if (query.isLoading || !query.data) body = <LoadingState />;
  else
    body = (
      <CodeMirrorEditor
        doc={displayText}
        settings={settings}
        dark={dark}
        editable
        onChange={onLocalChange}
        onBlur={saveNow}
      />
    );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b px-3 py-1.5">
        <span className="mr-auto truncate text-sm font-medium">
          {openEntity?.name ?? "No file open"}
        </span>
        {isDoc && <SaveStatusIndicator status={status} onRetry={saveNow} />}
        <EditorSettingsPopover settings={settings} onUpdate={update} />
      </div>
      <div className="min-h-0 flex-1">{body}</div>
      <ConflictDialog
        open={conflict !== null}
        onOpenChange={() => {
          /* stays open until resolved */
        }}
        onReload={resolveReload}
        onKeepMine={resolveKeepMine}
      />
    </div>
  );
}
