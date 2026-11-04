/**
 * The Suggesting switch (spec 119 §3), in the editor's status line beside the presence. The member's choice is
 * stored per project; it starts from the value the server returns, and a failed save puts the switch back.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

import { Switch } from "@/components/ui/switch";
import { type CollabDocSession, setSuggestMode } from "@/modules/collab";
import { usePermissions } from "@/modules/sharing";

/** Starts the switch from the stored preference, once per session. */
function useStoredPreference(projectId: string, session: CollabDocSession) {
  const { data } = usePermissions(projectId);
  const applied = useRef(false);
  useEffect(() => {
    if (applied.current || data === undefined) return;
    applied.current = true;
    session.suggest.setSuggesting(data.suggest_mode ?? false);
  }, [data, session.suggest]);
}

/** The switch for a member who can write the text. A viewer does not see it. */
export function SuggestSwitch({ session }: { session: CollabDocSession }) {
  const { t } = useTranslation("suggest");
  const controller = session.suggest;
  const on = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const [failed, setFailed] = useState(false);
  useStoredPreference(session.projectId, session);
  useEffect(() => {
    controller.onBlocked = () => toast.error(t("blocked"));
  }, [controller, t]);

  const toggle = (next: boolean) => {
    controller.setSuggesting(next);
    setFailed(false);
    setSuggestMode(session.projectId, next).catch(() => {
      controller.setSuggesting(!next);
      setFailed(true);
    });
  };

  return (
    <div className="flex items-center gap-2" title={t("mode.hint")}>
      <Switch id={`suggest-mode-${session.projectId}`} checked={on} onCheckedChange={toggle} />
      <label htmlFor={`suggest-mode-${session.projectId}`} className="cursor-pointer font-medium">
        {t("mode.label")}
      </label>
      {failed && (
        <span role="alert" className="text-error-text">
          {t("mode.failed")}
        </span>
      )}
    </div>
  );
}
