import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDebouncedValue } from "@/lib/use-debounced-value";

import { CreateProjectDialog, DeleteProjectDialog, RenameProjectDialog } from "./project-dialogs";
import { ProjectListView } from "./project-list-view";
import type { Project, SortKey } from "./types";
import { useProjects, visibleProjects } from "./use-projects";

type DialogState = { type: "create" | "rename" | "delete" | null; project?: Project };

export function ProjectsPage() {
  const projectsQuery = useProjects();
  const { logout } = useAuth();
  const navigate = useNavigate();

  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, 150);
  const [sortKey, setSortKey] = useState<SortKey>("updatedAt");
  const [dialog, setDialog] = useState<DialogState>({ type: null });

  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);
  const visible = useMemo(
    () => visibleProjects(projects, debouncedSearch, sortKey),
    [projects, debouncedSearch, sortKey],
  );

  const closeDialog = (open: boolean) => {
    if (!open) setDialog({ type: null });
  };

  const onLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between border-b px-6 py-3">
        <span className="font-semibold">Inkstave</span>
        <Button variant="outline" size="sm" onClick={onLogout}>
          Log out
        </Button>
      </header>
      <main className="mx-auto max-w-4xl space-y-6 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold">Your projects</h1>
          <Button onClick={() => setDialog({ type: "create" })}>
            <Plus />
            New project
          </Button>
        </div>

        <div className="flex flex-wrap gap-3">
          <Input
            aria-label="Search projects"
            placeholder="Search projects…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
          />
          <Select value={sortKey} onValueChange={(v) => setSortKey(v as SortKey)}>
            <SelectTrigger aria-label="Sort projects" className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="updatedAt">Last modified</SelectItem>
              <SelectItem value="name">Name A–Z</SelectItem>
              <SelectItem value="createdAt">Created</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <ProjectListView
          isLoading={projectsQuery.isLoading}
          isError={projectsQuery.isError}
          onRetry={() => void projectsQuery.refetch()}
          total={projects.length}
          searchTerm={debouncedSearch}
          visible={visible}
          onCreate={() => setDialog({ type: "create" })}
          onClearSearch={() => setSearch("")}
          onOpen={(p) => navigate(`/projects/${p.id}`)}
          onRename={(p) => setDialog({ type: "rename", project: p })}
          onDelete={(p) => setDialog({ type: "delete", project: p })}
        />
      </main>

      <CreateProjectDialog open={dialog.type === "create"} onOpenChange={closeDialog} />
      <RenameProjectDialog
        open={dialog.type === "rename"}
        onOpenChange={closeDialog}
        project={dialog.project ?? null}
      />
      <DeleteProjectDialog
        open={dialog.type === "delete"}
        onOpenChange={closeDialog}
        project={dialog.project ?? null}
      />
    </div>
  );
}
