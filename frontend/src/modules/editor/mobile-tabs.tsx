import { FileText, FileType, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { config } from "@/config";
import { cn } from "@/lib/utils";

export type MobileView = "content" | "preview";

function Tab({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "flex min-h-12 flex-1 items-center justify-center gap-1.5 text-small font-medium",
        pressed ? "bg-accent text-foreground" : "text-muted-foreground",
      )}
    >
      {children}
    </button>
  );
}

/** A phone shows one thing at a time, and the switch sits under the thumb (spec 107). */
export function MobileTabs({
  view,
  onView,
  agentOpen,
  onToggleAgent,
}: {
  view: MobileView;
  onView: (view: MobileView) => void;
  agentOpen: boolean;
  onToggleAgent: () => void;
}) {
  const { t } = useTranslation("editor");
  return (
    <nav
      aria-label={t("mobile.views")}
      className="flex shrink-0 divide-x border-t pb-[env(safe-area-inset-bottom)]"
    >
      <Tab pressed={view === "content"} onClick={() => onView("content")}>
        <FileText aria-hidden="true" className="size-4" />
        {t("mobile.content")}
      </Tab>
      <Tab pressed={view === "preview"} onClick={() => onView("preview")}>
        <FileType aria-hidden="true" className="size-4" />
        {t("mobile.preview")}
      </Tab>
      {config.agentEnabled && (
        <Tab pressed={agentOpen} onClick={onToggleAgent}>
          <Sparkles aria-hidden="true" className="size-4" />
          {t("toolbar.agent")}
        </Tab>
      )}
    </nav>
  );
}
