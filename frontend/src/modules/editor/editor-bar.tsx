import { ArrowLeft, Download, History, Share2, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { InkstaveMark } from "@/components/inkstave-logo";
import { Button } from "@/components/ui/button";
import { config } from "@/config";
import { NotificationsBell } from "@/modules/notifications";
import { useDownloadProject } from "@/modules/projects";

/** Tighter below `lg`, where five tools share the bar with the title. */
const TOOL_CLASS = "px-2 lg:px-3";

/** Icons only below `lg`, or the words squeeze out the title. The word stays as the control's name. */
function BarLabel({ children }: { children: string }) {
  return <span className="sr-only lg:not-sr-only">{children}</span>;
}

/** The editor's one bar (spec 106): what is open, the way back, and the workspace tools. */
export function EditorBar({
  projectId,
  projectName,
  agentOpen,
  onToggleAgent,
  historyDisabled,
  onOpenHistory,
  onOpenShare,
}: {
  projectId: string;
  projectName: string | undefined;
  agentOpen: boolean;
  onToggleAgent: () => void;
  historyDisabled: boolean;
  onOpenHistory: () => void;
  onOpenShare: () => void;
}) {
  const { t } = useTranslation(["editor", "common"]);
  const { download, downloadingId } = useDownloadProject();

  return (
    <header className="flex items-center gap-1 border-b px-3 py-1.5 lg:gap-2">
      <Link to="/projects" aria-label="Inkstave" className="shrink-0 hover:opacity-80">
        <InkstaveMark className="h-5 w-5 text-foreground" />
      </Link>
      <h1 className="min-w-0 flex-1 truncate font-serif text-heading font-medium">
        {projectName ?? t("common:state.loading")}
      </h1>
      <Link
        to="/projects"
        className="inline-flex size-8 shrink-0 items-center justify-center text-body text-muted-foreground hover:text-foreground lg:size-auto"
      >
        <ArrowLeft aria-hidden="true" className="size-4 lg:hidden" />
        <BarLabel>{t("toolbar.backToProjects")}</BarLabel>
      </Link>
      {config.agentEnabled && (
        <Button
          size="sm"
          variant={agentOpen ? "secondary" : "ghost"}
          className={TOOL_CLASS}
          aria-pressed={agentOpen}
          onClick={onToggleAgent}
        >
          <Sparkles aria-hidden="true" className="size-4" />
          <BarLabel>{t("toolbar.agent")}</BarLabel>
        </Button>
      )}
      <Button
        size="sm"
        variant="ghost"
        className={TOOL_CLASS}
        disabled={historyDisabled}
        onClick={onOpenHistory}
      >
        <History aria-hidden="true" className="size-4" />
        <BarLabel>{t("toolbar.history")}</BarLabel>
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className={TOOL_CLASS}
        disabled={downloadingId === projectId}
        aria-busy={downloadingId === projectId}
        onClick={() => void download(projectId, projectName ?? "project")}
      >
        <Download aria-hidden="true" className="size-4" />
        <BarLabel>{t("toolbar.download")}</BarLabel>
      </Button>
      <Button size="sm" variant="ghost" className={TOOL_CLASS} onClick={onOpenShare}>
        <Share2 aria-hidden="true" className="size-4" />
        <BarLabel>{t("toolbar.share")}</BarLabel>
      </Button>
      <NotificationsBell />
    </header>
  );
}
