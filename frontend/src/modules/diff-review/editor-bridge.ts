/** A DocumentBridge backed by transient collab providers (spec 47, live apply path). */
import { Awareness } from "y-protocols/awareness";
import * as Y from "yjs";

import { InkstaveWsProvider, collabDocUrl } from "@/modules/collab";
import { tokenStore } from "@/lib/token-store";

import { applySplicesToYText, applyTargetToYText } from "./crdt-apply";
import type { LiveTextBridge } from "./types";

/** How long a replace waits for a document's first sync before it gives up on that file (spec 122). */
export const SYNC_DEADLINE_MS = 10_000;

function withDeadline(ready: Promise<void>, ms: number): Promise<void> {
  let timer = 0;
  const late = new Promise<never>((_, reject) => {
    timer = window.setTimeout(() => reject(new Error("The document did not sync in time.")), ms);
  });
  return Promise.race([ready, late]).finally(() => window.clearTimeout(timer));
}

interface Entry {
  ydoc: Y.Doc;
  provider: InkstaveWsProvider;
  ready: Promise<void>;
}

/**
 * Opens a short-lived Yjs provider per target document, so an apply writes through the
 * CRDT and connected collaborators (incl. the editor's own binding for an open doc)
 * converge live. `resolveDocId` maps a project-relative path to its document id.
 */
export function createEditorBridge(
  projectId: string,
  resolveDocId: (path: string) => string | null,
): LiveTextBridge {
  const cache = new Map<string, Entry>();

  const open = (path: string): Entry | null => {
    const docId = resolveDocId(path);
    if (!docId) return null;
    let entry = cache.get(docId);
    if (!entry) {
      const ydoc = new Y.Doc();
      const provider = new InkstaveWsProvider({
        url: collabDocUrl(projectId, docId),
        documentId: docId,
        ydoc,
        awareness: new Awareness(ydoc),
        getToken: () => tokenStore.getAccessToken() ?? "",
      });
      const ready = provider.synced
        ? Promise.resolve()
        : new Promise<void>((resolve) => {
            provider.on("synced", (e) => {
              if (e.synced) resolve();
            });
          });
      entry = { ydoc, provider, ready };
      cache.set(docId, entry);
    }
    return entry;
  };

  return {
    async readContent(path) {
      const entry = open(path);
      if (!entry) return null;
      await entry.ready;
      return entry.ydoc.getText("content").toString();
    },
    async applyContent(path, target) {
      const entry = open(path);
      if (!entry) throw new Error(`Unknown file: ${path}`);
      await entry.ready;
      applyTargetToYText(entry.ydoc.getText("content"), target);
      await entry.provider.flush();
    },
    async transformContent(path, edit) {
      const entry = open(path);
      if (!entry) return null;
      await withDeadline(entry.ready, SYNC_DEADLINE_MS);
      const ytext = entry.ydoc.getText("content");
      applySplicesToYText(ytext, edit(ytext.toString()));
      await entry.provider.flush();
      return ytext.toString();
    },
    destroy() {
      for (const entry of cache.values()) entry.provider.destroy();
      cache.clear();
    },
  };
}
