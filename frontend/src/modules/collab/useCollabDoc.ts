/**
 * React hook owning one collaborative Yjs session per open document (spec 31):
 * the `Y.Doc`/`Y.Text('content')`, the `InkstaveWsProvider`, awareness, the
 * `y-codemirror.next` binding, and a reactive connection status. Exactly one
 * session per `documentId`; torn down on unmount or id change, idempotent under
 * React StrictMode's double-mount.
 */
import type { Extension } from "@codemirror/state";
import { useEffect, useRef, useState } from "react";
import { yCollab, ySync } from "y-codemirror.next";
import { Awareness } from "y-protocols/awareness";
import * as Y from "yjs";

import { config } from "@/config";

import { InkstaveWsProvider, type ProviderStatus } from "./InkstaveWsProvider";
import { remoteCursorTheme } from "./remote-cursors";
import {
  type SuggestionAuthor,
  type SuggestionFields,
  SUGGESTIONS_KEY,
  SuggestController,
  suggestExtension,
} from "./suggestions";
import { CURSOR_THROTTLE_MS } from "./usePresence";

export type CollabStatus = "connecting" | "connected" | "reconnecting" | "offline";

export interface CollabDocSession {
  projectId: string;
  ydoc: Y.Doc;
  text: Y.Text;
  provider: InkstaveWsProvider;
  awareness: Awareness;
  status: CollabStatus;
  synced: boolean;
  cmExtension: Extension;
  readOnly: boolean;
  /** The Suggesting switch of this session (spec 119). */
  suggest: SuggestController;
  /** Resolve once pending local edits have been sent (call before triggering a compile). */
  flush: () => Promise<void>;
}

interface CoreSession {
  projectId: string;
  ydoc: Y.Doc;
  text: Y.Text;
  provider: InkstaveWsProvider;
  awareness: Awareness;
  cmExtension: Extension;
  readOnly: boolean;
  suggest: SuggestController;
}

export interface UseCollabDocOptions {
  projectId: string;
  documentId: string | null;
  getToken: () => string | Promise<string>;
  enabled?: boolean;
  readOnly?: boolean;
  /** The local user, who authors the suggestions made in Suggesting mode (spec 119). */
  author?: SuggestionAuthor | null;
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
  const { projectId, documentId, enabled = true, readOnly = false, author = null } = options;
  const [core, setCore] = useState<CoreSession | null>(null);
  const [status, setStatus] = useState<CollabStatus>("connecting");
  const [synced, setSynced] = useState(false);

  // Keep getToken current without re-creating the session when its identity changes.
  const getTokenRef = useRef(options.getToken);
  getTokenRef.current = options.getToken;
  const authorRef = useRef(author);
  authorRef.current = author;

  useEffect(() => {
    if (!enabled || !documentId || !config.collabWsUrl) {
      setCore(null);
      return;
    }
    const ydoc = new Y.Doc();
    const text = ydoc.getText("content");
    const suggestions = ydoc.getMap<SuggestionFields>(SUGGESTIONS_KEY);
    const awareness = new Awareness(ydoc);
    // One undo reverts a suggestion's text and its record together, so both are in the undo scope (spec 119).
    const undoManager = new Y.UndoManager([text, suggestions]);
    const provider = new InkstaveWsProvider({
      url: collabDocUrl(projectId, documentId),
      documentId,
      ydoc,
      awareness,
      getToken: () => getTokenRef.current(),
      awarenessThrottleMs: CURSOR_THROTTLE_MS,
    });
    // `y-codemirror.next` scopes undo/redo to the local user via the undo manager, and renders remote
    // cursors/selections from awareness (spec 32 theme). Its sync plugin is replaced by the one of Suggesting
    // mode, which writes a suggestion's record in the same transaction as its text (spec 119 §5.3).
    const suggest = new SuggestController(() => authorRef.current, awareness);
    // The library returns its plugin list as an array.
    const collab = yCollab(text, awareness, { undoManager }) as Extension[];
    const cmExtension = [
      ...collab.filter((extension) => extension !== ySync),
      suggestExtension({ ytext: text, suggestions, controller: suggest, canDecide: !readOnly }),
      remoteCursorTheme,
    ];

    setStatus(mapStatus(provider.status));
    setSynced(provider.synced);
    const onStatus = (event: { status: ProviderStatus }) => setStatus(mapStatus(event.status));
    const onSynced = (event: { synced: boolean }) => setSynced(event.synced);
    provider.on("status", onStatus);
    provider.on("synced", onSynced);

    setCore({ projectId, ydoc, text, provider, awareness, cmExtension, readOnly, suggest });

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
