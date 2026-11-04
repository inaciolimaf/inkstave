import { Download, LogOut, Loader2, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import { formatDate } from "@/lib/formatting";

import { useDownloadProject } from "./use-download-project";
import { usePrefetchProject } from "./use-prefetch-project";
import type { ListedProject } from "./types";

interface RowActions {
  onOpen: (p: ListedProject) => void;
  onRename: (p: ListedProject) => void;
  onDelete: (p: ListedProject) => void;
  onLeave: (p: ListedProject) => void;
}

/** Owners rename and delete; editors and viewers leave. Everyone downloads (spec 109). */
export function RowActionsMenu({
  project,
  onOpen,
  onRename,
  onDelete,
  onLeave,
}: { project: ListedProject } & RowActions) {
  const { t } = useTranslation("projects");
  const { download, downloadingId } = useDownloadProject();
  const isDownloading = downloadingId === project.id;
  const isOwner = project.role === "owner";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("actionsMenu.label")}>
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => onOpen(project)}>{t("actionsMenu.open")}</DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(e) => {
            e.preventDefault(); // keep the menu open while the download is in flight
            void download(project.id, project.name);
          }}
          disabled={isDownloading}
          aria-busy={isDownloading}
        >
          {isDownloading ? <Loader2 className="animate-spin" /> : <Download />}
          {t("actionsMenu.download")}
        </DropdownMenuItem>
        {isOwner && (
          <DropdownMenuItem onSelect={() => onRename(project)}>
            <Pencil />
            {t("common:action.rename")}
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        {isOwner ? (
          <DropdownMenuItem
            onSelect={() => onDelete(project)}
            className="text-error-text focus:text-error-text"
          >
            <Trash2 />
            {t("common:action.delete")}
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem onSelect={() => onLeave(project)}>
            <LogOut />
            {t("actionsMenu.leave")}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The owner line: "You" for the caller's own projects, otherwise the owner's name and the caller's role. */
function OwnerLine({ project }: { project: ListedProject }) {
  const { t } = useTranslation("projects");
  const isOwner = project.role === "owner";
  return (
    <span className="flex min-w-0 items-baseline gap-2 text-small text-muted-foreground">
      <span className="truncate">{isOwner ? t("owner.you") : project.owner.displayName}</span>
      {!isOwner && (
        <Badge variant="outline" className="shrink-0 font-normal">
          {t(`role.${project.role}`)}
        </Badge>
      )}
    </span>
  );
}

/** The index of works: each project a line of a table of contents, title, leader and date. */
export function ProjectIndex({ projects, ...actions }: { projects: ListedProject[] } & RowActions) {
  const { t } = useTranslation("projects");
  const prefetchProject = usePrefetchProject();
  return (
    <ol aria-label={t("table.caption")}>
      {projects.map((project) => (
        <li key={project.id} className="flex items-center gap-2 border-b border-border">
          <div className="flex min-w-0 flex-1 flex-col gap-0.5 py-3 sm:flex-row sm:items-baseline sm:gap-3">
            <Link
              to={`/projects/${project.id}`}
              title={project.name}
              onPointerEnter={() => prefetchProject(project.id)}
              onFocus={() => prefetchProject(project.id)}
              className="truncate font-serif text-heading underline-offset-4 hover:underline"
            >
              {project.name}
            </Link>
            <OwnerLine project={project} />
            <span
              aria-hidden="true"
              className="hidden flex-1 border-b border-dotted border-border-strong sm:block"
            />
            <span className="whitespace-nowrap text-small tabular-nums text-muted-foreground">
              <span className="sr-only">{t("table.lastModified")}: </span>
              {formatDate(project.updatedAt)}
            </span>
          </div>
          <RowActionsMenu project={project} {...actions} />
        </li>
      ))}
    </ol>
  );
}
