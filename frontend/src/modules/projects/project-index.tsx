import { Download, Loader2, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

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
import type { Project } from "./types";

interface RowActions {
  onOpen: (p: Project) => void;
  onRename: (p: Project) => void;
  onDelete: (p: Project) => void;
}

export function RowActionsMenu({ project, onOpen, onRename, onDelete }: { project: Project } & RowActions) {
  const { t } = useTranslation("projects");
  const { download, downloadingId } = useDownloadProject();
  const isDownloading = downloadingId === project.id;
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
        <DropdownMenuItem onSelect={() => onRename(project)}>
          <Pencil />
          {t("common:action.rename")}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => onDelete(project)}
          className="text-error-text focus:text-error-text"
        >
          <Trash2 />
          {t("common:action.delete")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The index of works: each project a line of a table of contents, title, leader and date. */
export function ProjectIndex({ projects, ...actions }: { projects: Project[] } & RowActions) {
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
