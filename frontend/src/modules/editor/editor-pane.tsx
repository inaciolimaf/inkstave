import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { EditorView } from "@codemirror/view";
import { FileText, LocateFixed } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CollabEditor } from "./CollabEditor";
import { useCollabDoc } from "@/modules/collab";
import { ApiError } from "@/lib/api-client";
import { useShortcuts } from "@/lib/shortcuts";
import type { TreeEntity } from "@/modules/file-tree";

import { getDocument } from "./api";
import { useDocumentAutosave, type DocumentAutosave } from "./autosave/use-document-autosave";
import { CodeMirrorEditor } from "./codemirror-editor";
import { ConflictDialog } from "./conflict-dialog";
import { EditorSettingsPopover } from "./editor-settings-popover";
import { SaveStatusIndicator } from "./save-status-indicator";
import type { EditorSettings } from "./types";
import { documentKey } from "./use-document";
import { useEditorPreferences } from "./use-editor-preferences";

function EmptyState() {
  const { t } = useTranslation("editor");
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-body text-muted-foreground">
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

function BinaryNotice() {
  const { t } = useTranslation("editor");
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-body text-muted-foreground">
      <FileText className="size-8" />
      <p>{t("pane.binaryFile")}</p>
    </div>
  );
}

interface EditorPaneProps {
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
}

/** The open entity, its REST content and its collab session. */
function useOpenDocument({
  projectId,
  selected,
  onClearSelection,
  collabEnabled,
  getToken,
  readOnly,
}: Pick<EditorPaneProps, "projectId" | "selected" | "onClearSelection" | "getToken"> & {
  collabEnabled: boolean;
  readOnly: boolean;
}) {
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

  const notFound = query.error instanceof ApiError && query.error.status === 404;
  useEffect(() => {
    if (notFound) {
      setOpenEntity(null);
      onClearSelection();
    }
  }, [notFound, onClearSelection]);

  const loaded = isDoc && query.data ? query.data : null;
  return { openEntity, isDoc, query, notFound, collabActive, collabSession, loaded };
}

function PaneBody({
  document: { openEntity, query, notFound, collabActive, collabSession },
  autosave,
  settings,
  dark,
  onEditorView,
  currentUser,
}: {
  document: ReturnType<typeof useOpenDocument>;
  autosave: DocumentAutosave;
  settings: EditorSettings;
  dark: boolean;
  onEditorView: EditorPaneProps["onEditorView"];
  currentUser: { id: string; name: string } | null;
}) {
  const { t } = useTranslation("editor");
  if (!openEntity) return <EmptyState />;
  if (openEntity.type === "file") return <BinaryNotice />;
  if (collabActive) {
    // Live CRDT editing (spec 31): content + sync come from the WebSocket, not REST.
    if (!collabSession) return <LoadingState />;
    return (
      <CollabEditor
        session={collabSession}
        settings={settings}
        dark={dark}
        onView={onEditorView}
        currentUser={currentUser}
      />
    );
  }
  return (
    <QueryView
      query={query}
      loading={<LoadingState />}
      errorMessage={notFound ? t("pane.documentGone") : t("pane.loadFailed")}
      errorClassName="h-full flex-col justify-center"
    >
      {() => (
        <CodeMirrorEditor
          doc={autosave.displayText}
          settings={settings}
          dark={dark}
          editable
          onChange={autosave.onLocalChange}
          onBlur={autosave.saveNow}
          onView={onEditorView}
        />
      )}
    </QueryView>
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
}: EditorPaneProps) {
  const { t } = useTranslation("editor");
  const { settings, dark, update } = useEditorPreferences();
  const openDocument = useOpenDocument({
    projectId,
    selected,
    onClearSelection,
    collabEnabled,
    getToken,
    readOnly,
  });
  const { openEntity, isDoc, collabActive, loaded } = openDocument;
  const autosave = useDocumentAutosave(projectId, loaded);
  const { status, hasUnsaved, conflict, lastSavedAt, saveNow, resolveReload, resolveKeepMine } = autosave;

  useEffect(() => {
    onDirtyChange?.(hasUnsaved);
  }, [hasUnsaved, onDirtyChange]);

  // Notify when the open document's content is ready (deferred SyncTeX reveal).
  useEffect(() => {
    if (loaded && openEntity?.type === "doc") onDocumentLoaded?.(openEntity);
    // Fires once per loaded document: a refetch or a new callback identity is not a new load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded?.id]);

  // Ctrl/Cmd+S forces an immediate flush and suppresses the browser save dialog.
  useShortcuts({ "mod+s": () => saveNow() }, isDoc);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b px-3 py-1.5">
        <span className="mr-auto truncate font-serif text-heading">
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
      <div className="min-h-0 flex-1">
        <PaneBody
          document={openDocument}
          autosave={autosave}
          settings={settings}
          dark={dark}
          onEditorView={onEditorView}
          currentUser={currentUser}
        />
      </div>
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
