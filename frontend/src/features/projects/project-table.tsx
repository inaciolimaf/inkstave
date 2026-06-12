import { Download, Loader2, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import { useDownloadProject } from "./use-download-project";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import type { Project } from "./types";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

interface RowActions {
  onOpen: (p: Project) => void;
  onRename: (p: Project) => void;
  onDelete: (p: Project) => void;
}

export function RowActionsMenu({
  project,
  onOpen,
  onRename,
  onDelete,
}: { project: Project } & RowActions) {
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
        <DropdownMenuItem onSelect={() => onOpen(project)}>
          {t("actionsMenu.open")}
        </DropdownMenuItem>
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
          className="text-destructive focus:text-destructive"
        >
          <Trash2 />
          {t("common:action.delete")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ProjectTable({ projects, ...actions }: { projects: Project[] } & RowActions) {
  const { t } = useTranslation("projects");
  return (
    <Table>
      <TableCaption className="sr-only">{t("table.caption")}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead>{t("table.name")}</TableHead>
          <TableHead>{t("table.lastModified")}</TableHead>
          <TableHead className="w-12 text-right">
            <span className="sr-only">{t("table.actions")}</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {projects.map((project) => (
          <TableRow key={project.id}>
            <TableCell className="font-medium">
              <Link to={`/projects/${project.id}`} className="hover:underline">
                {project.name}
              </Link>
            </TableCell>
            <TableCell className="text-muted-foreground">{formatDate(project.updatedAt)}</TableCell>
            <TableCell className="text-right">
              <RowActionsMenu project={project} {...actions} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function ProjectCardGrid({ projects, ...actions }: { projects: Project[] } & RowActions) {
  const { t } = useTranslation("projects");
  return (
    <ul className="grid gap-3">
      {projects.map((project) => (
        <li key={project.id}>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-base">
                <Link to={`/projects/${project.id}`} className="hover:underline">
                  {project.name}
                </Link>
              </CardTitle>
              <RowActionsMenu project={project} {...actions} />
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              {t("card.lastModified", { date: formatDate(project.updatedAt) })}
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
