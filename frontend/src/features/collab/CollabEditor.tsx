/**
 * The live-collaborative editor (spec 31/32): binds a {@link CollabDocSession}'s
 * `Y.Text` to CodeMirror via `y-codemirror.next`, gates editing until the first
 * sync, shows the connection badge + the "online now" list, and publishes the
 * local user's presence (identity + cursor + idle) through Yjs awareness.
 */
import type { EditorView } from "@codemirror/view";
import { useTranslation } from "react-i18next";

import { CodeMirrorEditor } from "@/features/editor/codemirror-editor";
import type { EditorSettings } from "@/features/editor/types";

import { ConnectionStatusBadge } from "./ConnectionStatusBadge";
import { OnlineUsers } from "./OnlineUsers";
import type { CollabDocSession } from "./useCollabDoc";
import { usePresence } from "./usePresence";

function LoadingOverlay() {
  const { t } = useTranslation("editor");
  return (
    <div
      className="absolute inset-0 z-10 flex items-center justify-center bg-background/60 backdrop-blur-[1px]"
      aria-label={t("collab.loadingDocument")}
      aria-busy="true"
    >
      <p className="text-sm text-muted-foreground">{t("collab.loadingDocument")}</p>
    </div>
  );
}

export function CollabEditor({
  session,
  settings,
  dark,
  onView,
  currentUser = null,
}: {
  session: CollabDocSession;
  settings: EditorSettings;
  dark: boolean;
  onView?: (view: EditorView | null) => void;
  /** Local user identity published into awareness (presence); null hides own presence. */
  currentUser?: { id: string; name: string } | null;
}) {
  const { t } = useTranslation("editor");
  const editable = session.synced && !session.readOnly;
  const { users, markActivity } = usePresence(session, currentUser);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b px-3 py-1 text-xs">
        <ConnectionStatusBadge status={session.status} />
        {!session.synced && <span className="text-muted-foreground">{t("collab.syncing")}</span>}
        {session.readOnly && (
          <span
            className="rounded bg-amber-500/15 px-1.5 py-0.5 font-medium text-amber-600 dark:text-amber-400"
            aria-live="polite"
          >
            {t("collab.viewOnly")}
          </span>
        )}
        <div className="ml-auto">
          <OnlineUsers users={users} />
        </div>
      </div>
      <div
        className="relative min-h-0 flex-1"
        onKeyDownCapture={markActivity}
        onMouseUp={markActivity}
      >
        {!session.synced && <LoadingOverlay />}
        <CodeMirrorEditor
          doc=""
          settings={settings}
          dark={dark}
          editable={editable}
          onView={onView}
          collabExtension={session.cmExtension}
        />
      </div>
    </div>
  );
}
