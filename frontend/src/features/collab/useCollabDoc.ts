/**
 * React hook owning one collaborative Yjs session per open document (spec 31):
 * the `Y.Doc`/`Y.Text('content')`, the `InkstaveWsProvider`, awareness, the
 * `y-codemirror.next` binding, and a reactive connection status. Exactly one
 * session per `documentId`; torn down on unmount or id change, idempotent under
 * React StrictMode's double-mount.
 */
import type { Extension } from "@codemirror/state";
import { useEffect, useRef, useState } from "react";
import { yCollab } from "y-codemirror.next";
import { Awareness } from "y-protocols/awareness";
import * as Y from "yjs";

import { config } from "@/config";

import { InkstaveWsProvider, type ProviderStatus } from "./InkstaveWsProvider";
import { remoteCursorTheme } from "./remote-cursors";
import { CURSOR_THROTTLE_MS } from "./usePresence";

export type CollabStatus = "connecting" | "connected" | "reconnecting" | "offline";

export interface CollabDocSession {
  ydoc: Y.Doc;
  text: Y.Text;
  provider: InkstaveWsProvider;
  awareness: Awareness;
  status: CollabStatus;
  synced: boolean;
  cmExtension: Extension;
  readOnly: boolean;
  /** Resolve once pending local edits have been sent (call before triggering a compile). */
  flush: () => Promise<void>;
}

interface CoreSession {
  ydoc: Y.Doc;
  text: Y.Text;
  provider: InkstaveWsProvider;
  awareness: Awareness;
  cmExtension: Extension;
  readOnly: boolean;
}

export interface UseCollabDocOptions {
  projectId: string;
  documentId: string | null;
  getToken: () => string | Promise<string>;
  enabled?: boolean;
  readOnly?: boolean;
}

export function collabDocUrl(projectId: string, documentId: string): string {
  return `${config.collabWsUrl}/projects/${projectId}/documents/${documentId}`;
}

function mapStatus(status: ProviderStatus): CollabStatus {
  if (status === "connected") return "connected";
  if (status === "reconnecting") return "reconnecting";
  if (status === "closed") return "offline";
  return "connecting"; // idle | connecting
}

export function useCollabDoc(options: UseCollabDocOptions): CollabDocSession | null {
  const { projectId, documentId, enabled = true, readOnly = false } = options;
  const [core, setCore] = useState<CoreSession | null>(null);
  const [status, setStatus] = useState<CollabStatus>("connecting");
  const [synced, setSynced] = useState(false);

  // Keep getToken current without re-creating the session when its identity changes.
  const getTokenRef = useRef(options.getToken);
  getTokenRef.current = options.getToken;

  useEffect(() => {
    if (!enabled || !documentId || !config.collabWsUrl) {
      setCore(null);
      return;
    }
    const ydoc = new Y.Doc();
    const text = ydoc.getText("content");
    const awareness = new Awareness(ydoc);
    const undoManager = new Y.UndoManager(text);
    const provider = new InkstaveWsProvider({
      url: collabDocUrl(projectId, documentId),
      documentId,
      ydoc,
      awareness,
      getToken: () => getTokenRef.current(),
      awarenessThrottleMs: CURSOR_THROTTLE_MS,
    });
    // `y-codemirror.next` scopes undo/redo to the local user via the undo manager,
    // and renders remote cursors/selections from awareness (spec 32 theme).
    const cmExtension = [yCollab(text, awareness, { undoManager }), remoteCursorTheme];

    setStatus(mapStatus(provider.status));
    setSynced(provider.synced);
    const onStatus = (event: { status: ProviderStatus }) => setStatus(mapStatus(event.status));
    const onSynced = (event: { synced: boolean }) => setSynced(event.synced);
    provider.on("status", onStatus);
    provider.on("synced", onSynced);

    setCore({ ydoc, text, provider, awareness, cmExtension, readOnly });

    return () => {
      provider.off("status", onStatus);
      provider.off("synced", onSynced);
      provider.destroy();
      undoManager.destroy();
      awareness.destroy();
      ydoc.destroy();
      setCore(null);
    };
  }, [projectId, documentId, enabled, readOnly]);

  if (core === null) return null;
  return { ...core, status, synced, flush: () => core.provider.flush() };
}
