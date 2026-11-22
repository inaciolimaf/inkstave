import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { EditorView } from "@codemirror/view";
import { LocateFixed } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CollabEditor } from "./CollabEditor";
import { type CollabDocSession, useCollabDoc } from "@/modules/collab";
import { ApiError } from "@/lib/api-client";
import { useShortcuts } from "@/lib/shortcuts";
import type { TreeEntity } from "@/modules/file-tree";
import { useSpellcheck, type SpellcheckBinding } from "@/modules/spellcheck";

import { getDocument } from "./api";
import { EditorSettingsPopover } from "./editor-settings-popover";
import { FilePreview } from "./file-preview";
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

interface EditorPaneProps {
  projectId: string;
  selected: TreeEntity | null;
  onClearSelection: () => void;
  /** Exposes the CodeMirror view for SyncTeX reveal (spec 26). */
  onEditorView?: (view: EditorView | null) => void;
  /** "Sync to PDF" (forward sync) clicked for the open document. */
  onSyncToPdf?: () => void;
  /** Fires when the open document's content has loaded (for deferred reveal). */
  onDocumentLoaded?: (entity: TreeEntity) => void;
  /** Whether forward sync is available (a successful compile exists). */
  syncEnabled?: boolean;
  /** Access-token getter for the collab WebSocket. */
  getToken?: () => string | Promise<string>;
  /** Local user identity for presence (spec 32). */
  currentUser?: { id: string; name: string } | null;
  /** Viewer role → mount the collab editor read-only (spec 34). */
  readOnly?: boolean;
  /** The status line these tools live in (spec 107); `undefined` keeps them in a row of their own. */
  statusSlot?: HTMLElement | null;
  /** Hands the collab session's flush to the workspace, so a compile or an agent turn can wait for it. */
  registerFlush?: (flush: (() => Promise<void>) | null) => void;
}

/** Registers the open collab session's flush while it lives; clears it on change and unmount. */
function useRegisterCollabFlush(
  collabSession: CollabDocSession | null,
  registerFlush: EditorPaneProps["registerFlush"],
) {
  const flush = collabSession?.flush ?? null;
  useEffect(() => {
    registerFlush?.(flush);
    return () => registerFlush?.(null);
  }, [flush, registerFlush]);
}

/** The open entity, its REST content and its collab session. */
function useOpenDocument({
  projectId,
  selected,
  onClearSelection,
  getToken,
  readOnly,
  currentUser,
}: Pick<EditorPaneProps, "projectId" | "selected" | "onClearSelection" | "getToken" | "currentUser"> & {
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
  const collabSession = useCollabDoc({
    projectId,
    documentId: docId,
    getToken: getToken ?? (() => ""),
    enabled: isDoc,
    readOnly,
    author: currentUser,
  });

  const notFound = query.error instanceof ApiError && query.error.status === 404;
  useEffect(() => {
    if (notFound) {
      setOpenEntity(null);
      onClearSelection();
    }
  }, [notFound, onClearSelection]);

  const loaded = isDoc && query.data ? query.data : null;
  return { projectId, openEntity, isDoc, collabSession, loaded };
}

function PaneBody({
  document: { projectId, openEntity, collabSession },
  settings,
  dark,
  onEditorView,
  currentUser,
  statusSlot,
  spellcheck,
}: {
  document: ReturnType<typeof useOpenDocument>;
  settings: EditorSettings;
  dark: boolean;
  onEditorView: EditorPaneProps["onEditorView"];
  currentUser: { id: string; name: string } | null;
  statusSlot: HTMLElement | null | undefined;
  spellcheck: SpellcheckBinding | null;
}) {
  if (!openEntity) return <EmptyState />;
  if (openEntity.type === "file") return <FilePreview projectId={projectId} entity={openEntity} />;
  // Live CRDT editing (spec 31): content + sync come from the WebSocket, not REST.
  if (!collabSession) return <LoadingState />;
  return (
    <CollabEditor
      session={collabSession}
      settings={settings}
      dark={dark}
      onView={onEditorView}
      currentUser={currentUser}
      statusSlot={statusSlot}
      spellcheck={spellcheck}
    />
  );
}

export function EditorPane({
  projectId,
  selected,
  onClearSelection,
  onEditorView,
  onSyncToPdf,
  onDocumentLoaded,
  syncEnabled = false,
  getToken,
  currentUser = null,
  readOnly = false,
  statusSlot,
  registerFlush,
}: EditorPaneProps) {
  const { t } = useTranslation("editor");
  const { settings, dark, update } = useEditorPreferences();
  const openDocument = useOpenDocument({
    projectId,
    selected,
    onClearSelection,
    getToken,
    readOnly,
    currentUser,
  });
  useRegisterCollabFlush(openDocument.collabSession, registerFlush);
  const { openEntity, isDoc, collabSession, loaded } = openDocument;
  const spell = useSpellcheck(projectId, openEntity?.type === "doc" ? openEntity.id : null);

  // Notify when the open document's content is ready (deferred SyncTeX reveal).
  useEffect(() => {
    if (loaded && openEntity?.type === "doc") onDocumentLoaded?.(openEntity);
    // Fires once per loaded document: a refetch or a new callback identity is not a new load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded?.id]);

  // Ctrl/Cmd+S waits for the server to hold every local edit, and suppresses the browser save dialog.
  useShortcuts({ "mod+s": () => void collabSession?.flush() }, isDoc);

  const tools = (
    <>
      {spell.failed && (
        <span role="status" className="text-small text-muted-foreground">
          {t("spellcheck.unavailable")}
        </span>
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
    </>
  );

  return (
    <div className="flex h-full flex-col">
      {statusSlot === undefined ? (
        <div className="flex items-center gap-2 border-b px-3 py-1.5">
          <span className="mr-auto truncate font-serif text-heading">
            {openEntity?.name ?? t("pane.noFileOpen")}
          </span>
          {tools}
        </div>
      ) : (
        statusSlot && createPortal(tools, statusSlot)
      )}
      <div className="min-h-0 flex-1">
        <PaneBody
          document={openDocument}
          settings={settings}
          dark={dark}
          onEditorView={onEditorView}
          currentUser={currentUser}
          statusSlot={statusSlot}
          spellcheck={spell.binding}
        />
      </div>
    </div>
  );
}
