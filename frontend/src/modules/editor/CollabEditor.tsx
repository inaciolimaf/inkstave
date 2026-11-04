/**
 * The live-collaborative editor (spec 31/32): binds a {@link CollabDocSession}'s
 * `Y.Text` to CodeMirror via `y-codemirror.next`, gates editing until the first
 * sync, shows the connection badge + the "online now" list, and publishes the
 * local user's presence (identity + cursor + idle) through Yjs awareness.
 */
import type { EditorView } from "@codemirror/view";
import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { CodeMirrorEditor } from "./codemirror-editor";
import { SuggestSwitch } from "./suggest-switch";
import type { EditorSettings } from "./types";

import { ConnectionStatusBadge, OnlineUsers, usePresence } from "@/modules/collab";
import type { CollabDocSession } from "@/modules/collab";
import type { SpellcheckBinding } from "@/modules/spellcheck";

function LoadingOverlay() {
  const { t } = useTranslation("editor");
  return (
    <div
      className="absolute inset-0 z-10 flex items-center justify-center bg-background/60 backdrop-blur-[1px]"
      aria-label={t("collab.loadingDocument")}
      aria-busy="true"
    >
      <p className="text-body text-muted-foreground">{t("collab.loadingDocument")}</p>
    </div>
  );
}

export function CollabEditor({
  session,
  settings,
  dark,
  onView,
  currentUser = null,
  statusSlot,
  spellcheck = null,
}: {
  session: CollabDocSession;
  settings: EditorSettings;
  dark: boolean;
  onView?: (view: EditorView | null) => void;
  /** Local user identity published into awareness (presence); null hides own presence. */
  currentUser?: { id: string; name: string } | null;
  /** The status line these indicators live in (spec 107); `undefined` keeps them in a row of their own. */
  statusSlot?: HTMLElement | null;
  /** Spell check for the open document (spec 113). */
  spellcheck?: SpellcheckBinding | null;
}) {
  const { t } = useTranslation("editor");
  const editable = session.synced && !session.readOnly;
  const { users, markActivity } = usePresence(session, currentUser);
  const { suggest } = session;
  useEffect(() => suggest.setEnabled(editable), [suggest, editable]);

  const indicators = (
    <>
      <ConnectionStatusBadge status={session.status} />
      {editable && <SuggestSwitch session={session} />}
      {!session.synced && <span className="text-muted-foreground">{t("collab.syncing")}</span>}
      {session.readOnly && (
        <span className="font-medium text-warning-text" aria-live="polite">
          {t("collab.viewOnly")}
        </span>
      )}
      <div className={statusSlot === undefined ? "ml-auto" : undefined}>
        <OnlineUsers users={users} />
      </div>
    </>
  );

  return (
    <div className="flex h-full flex-col">
      {statusSlot === undefined ? (
        <div className="flex items-center gap-2 border-b px-3 py-1 text-small">{indicators}</div>
      ) : (
        statusSlot && createPortal(indicators, statusSlot)
      )}
      <div className="relative min-h-0 flex-1" onKeyDownCapture={markActivity} onMouseUp={markActivity}>
        {!session.synced && <LoadingOverlay />}
        {/* The binding is fixed for the life of a view, so a new session needs a new view. */}
        <CodeMirrorEditor
          key={session.ydoc.guid}
          doc=""
          settings={settings}
          dark={dark}
          editable={editable}
          onView={onView}
          collabExtension={session.cmExtension}
          spellcheck={spellcheck}
        />
      </div>
    </div>
  );
}
