import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
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
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Project actions">
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => onOpen(project)}>Open</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onRename(project)}>
          <Pencil />
          Rename
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => onDelete(project)}
          className="text-destructive focus:text-destructive"
        >
          <Trash2 />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ProjectTable({ projects, ...actions }: { projects: Project[] } & RowActions) {
  return (
    <Table>
      <TableCaption className="sr-only">Your projects</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Last modified</TableHead>
          <TableHead className="w-12 text-right">
            <span className="sr-only">Actions</span>
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
              Last modified {formatDate(project.updatedAt)}
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
