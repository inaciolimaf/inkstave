import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { EditorView } from "@codemirror/view";
import { FileText, LocateFixed } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CollabEditor } from "@/features/collab/CollabEditor";
import { useCollabDoc } from "@/features/collab/useCollabDoc";
import { ApiError } from "@/lib/api-client";
import type { TreeEntity } from "@/features/file-tree/types";

import { getDocument } from "./api";
import { useDocumentAutosave } from "./autosave/use-document-autosave";
import { CodeMirrorEditor } from "./codemirror-editor";
import { ConflictDialog } from "./conflict-dialog";
import { EditorSettingsPopover } from "./editor-settings-popover";
import { SaveStatusIndicator } from "./save-status-indicator";
import { documentKey } from "./use-document";
import { useEditorPreferences } from "./use-editor-preferences";

function EmptyState() {
  const { t } = useTranslation("editor");
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
      {t("pane.selectFile")}
    </div>
  );
}

function LoadingState() {
  const { t } = useTranslation("editor");
  return (
    <div className="space-y-2 p-4" aria-busy="true" aria-label={t("pane.loadingDocument")}>
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-4" style={{ width: `${90 - (i % 4) * 12}%` }} />
      ))}
    </div>
  );
}

function ErrorState({ onRetry, notFound }: { onRetry: () => void; notFound: boolean }) {
  const { t } = useTranslation("editor");
  return (
    <div role="alert" className="flex h-full flex-col items-center justify-center gap-3 text-sm">
      <p className="text-destructive">{notFound ? t("pane.documentGone") : t("pane.loadFailed")}</p>
      {!notFound && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          {t("pane.retry")}
        </Button>
      )}
    </div>
  );
}

function BinaryNotice() {
  const { t } = useTranslation("editor");
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
      <FileText className="size-8" />
      <p>{t("pane.binaryFile")}</p>
    </div>
  );
}

export function EditorPane({
  projectId,
  selected,
  onClearSelection,
  onDirtyChange,
  onEditorView,
  onSyncToPdf,
  onDocumentLoaded,
  syncEnabled = false,
  collabEnabled = false,
  getToken,
  currentUser = null,
  readOnly = false,
}: {
  projectId: string;
  selected: TreeEntity | null;
  onClearSelection: () => void;
  onDirtyChange?: (dirty: boolean) => void;
  /** Exposes the CodeMirror view for SyncTeX reveal (spec 26). */
  onEditorView?: (view: EditorView | null) => void;
  /** "Sync to PDF" (forward sync) clicked for the open document. */
  onSyncToPdf?: () => void;
  /** Fires when the open document's content has loaded (for deferred reveal). */
  onDocumentLoaded?: (entity: TreeEntity) => void;
  /** Whether forward sync is available (a successful compile exists). */
  syncEnabled?: boolean;
  /** Use the live CRDT editor (spec 31) instead of REST autosave for documents. */
  collabEnabled?: boolean;
  /** Access-token getter for the collab WebSocket (required when collabEnabled). */
  getToken?: () => string | Promise<string>;
  /** Local user identity for presence (spec 32). */
  currentUser?: { id: string; name: string } | null;
  /** Viewer role → mount the collab editor read-only (spec 34). */
  readOnly?: boolean;
}) {
  const { t } = useTranslation("editor");
  const { settings, dark, update } = useEditorPreferences();

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
  const collabActive = collabEnabled && isDoc;
  const collabSession = useCollabDoc({
    projectId,
    documentId: collabActive ? docId : null,
    getToken: getToken ?? (() => ""),
    enabled: collabActive,
    readOnly,
  });
  const loaded = isDoc && query.data ? query.data : null;
  const {
    status,
    displayText,
    hasUnsaved,
    conflict,
    lastSavedAt,
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

  // Notify when the open document's content is ready (deferred SyncTeX reveal).
  useEffect(() => {
    if (loaded && openEntity?.type === "doc") onDocumentLoaded?.(openEntity);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded?.id]);

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
  else if (collabActive)
    // Live CRDT editing (spec 31): content + sync come from the WebSocket, not REST.
    body = collabSession ? (
      <CollabEditor
        session={collabSession}
        settings={settings}
        dark={dark}
        onView={onEditorView}
        currentUser={currentUser}
      />
    ) : (
      <LoadingState />
    );
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
        onView={onEditorView}
      />
    );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b px-3 py-1.5">
        <span className="mr-auto truncate text-sm font-medium">
          {openEntity?.name ?? t("pane.noFileOpen")}
        </span>
        {isDoc && !collabActive && (
          <SaveStatusIndicator status={status} onRetry={saveNow} lastSavedAt={lastSavedAt} />
        )}
        {isDoc && onSyncToPdf && (
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label={t("pane.syncToPdf")}
            title={t("pane.syncToPdfTitle")}
            disabled={!syncEnabled}
            onClick={onSyncToPdf}
          >
            <LocateFixed aria-hidden="true" />
          </Button>
        )}
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
