import { ChevronDown, ClipboardList, Download, History, MoreHorizontal, Share2, Undo2 } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { InkstaveMark } from "@/components/inkstave-logo";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { NotificationsBell } from "@/modules/notifications";
import { useDownloadProject } from "@/modules/projects";
import { SpellingMenuItems } from "@/modules/spellcheck";

/** The tools a person reaches for now and then wait in one menu, so the bar stays one quiet row. */
function MoreMenu({
  projectId,
  projectName,
  historyDisabled,
  readOnly,
  onOpenHistory,
  onOpenShare,
  onOpenCompatReport,
}: {
  projectId: string;
  projectName: string | undefined;
  historyDisabled: boolean;
  readOnly: boolean;
  onOpenHistory: () => void;
  onOpenShare: () => void;
  onOpenCompatReport?: () => void;
}) {
  const { t } = useTranslation("editor");
  const { download, downloadingId } = useDownloadProject();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="icon" variant="ghost" className="size-8" aria-label={t("toolbar.more")}>
          <MoreHorizontal aria-hidden="true" className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <SpellingMenuItems projectId={projectId} readOnly={readOnly} />
        <DropdownMenuItem disabled={historyDisabled} onSelect={onOpenHistory}>
          <History aria-hidden="true" className="size-4" />
          {t("toolbar.history")}
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={downloadingId === projectId}
          onSelect={() => void download(projectId, projectName ?? "project")}
        >
          <Download aria-hidden="true" className="size-4" />
          {t("toolbar.download")}
        </DropdownMenuItem>
        <DropdownMenuItem className="md:hidden" onSelect={onOpenShare}>
          <Share2 aria-hidden="true" className="size-4" />
          {t("toolbar.share")}
        </DropdownMenuItem>
        {onOpenCompatReport && (
          <DropdownMenuItem onSelect={onOpenCompatReport}>
            <ClipboardList aria-hidden="true" className="size-4" />
            {t("toolbar.compatReport")}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem asChild>
          <Link to="/projects">
            <Undo2 aria-hidden="true" className="size-4" />
            {t("toolbar.backToProjects")}
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * The editor's one bar (specs 106, 107): where you are, the one main action and little else. The
 * Compile button arrives through `compileSlotRef`: it belongs to the preview, which owns the compile.
 */
export function EditorBar({
  projectId,
  projectName,
  fileName,
  onOpenFiles,
  compileSlotRef,
  historyDisabled,
  readOnly = false,
  onOpenHistory,
  onOpenShare,
  insert,
  chatButton,
  onOpenCompatReport,
}: {
  projectId: string;
  projectName: string | undefined;
  fileName: string | undefined;
  onOpenFiles: () => void;
  compileSlotRef: (element: HTMLDivElement | null) => void;
  historyDisabled: boolean;
  /** Viewers may not change the spell-check language (spec 113). */
  readOnly?: boolean;
  onOpenHistory: () => void;
  onOpenShare: () => void;
  /** The Insert menu (spec 114); it needs the open document, so the workspace renders it. */
  insert?: ReactNode;
  /** The project chat's button, with its unread count (spec 117). */
  chatButton?: ReactNode;
  onOpenCompatReport?: () => void;
}) {
  const { t } = useTranslation(["editor", "common"]);
  return (
    <header className="flex items-center gap-2 border-b px-3 py-1.5">
      <Link to="/projects" aria-label="Inkstave" className="shrink-0 hover:opacity-80">
        <InkstaveMark className="h-5 w-5 text-foreground" />
      </Link>
      <h1 className="sr-only min-w-0 truncate font-serif text-heading font-medium md:not-sr-only">
        {projectName ?? t("common:state.loading")}
      </h1>
      <span aria-hidden="true" className="hidden text-muted-foreground md:inline">
        /
      </span>
      <button
        type="button"
        onClick={onOpenFiles}
        aria-label={t("toolbar.switchFile", { name: fileName ?? t("toolbar.noFile") })}
        className="flex min-h-8 min-w-0 items-center gap-1 rounded px-1.5 font-mono text-small hover:bg-accent"
      >
        <span className="truncate">{fileName ?? t("toolbar.files")}</span>
        <ChevronDown aria-hidden="true" className="size-4 shrink-0" />
      </button>
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <Button size="sm" variant="ghost" className="hidden md:inline-flex" onClick={onOpenShare}>
          <Share2 aria-hidden="true" className="size-4" />
          {t("toolbar.share")}
        </Button>
        {insert}
        {chatButton}
        <NotificationsBell />
        <MoreMenu
          projectId={projectId}
          projectName={projectName}
          historyDisabled={historyDisabled}
          readOnly={readOnly}
          onOpenHistory={onOpenHistory}
          onOpenShare={onOpenShare}
          onOpenCompatReport={onOpenCompatReport}
        />
        <div ref={compileSlotRef} className="contents" />
      </div>
    </header>
  );
}
