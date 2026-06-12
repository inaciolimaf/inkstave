import { FolderPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { ProjectCardGrid, ProjectTable } from "./project-table";
import type { Project } from "./types";

function ProjectListSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading projects">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

function ProjectListEmpty({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-lg border border-dashed p-12 text-center">
      <FolderPlus className="size-10 text-muted-foreground" />
      <div>
        <p className="font-medium">No projects yet</p>
        <p className="text-sm text-muted-foreground">Create your first project to get started.</p>
      </div>
      <Button onClick={onCreate}>Create your first project</Button>
    </div>
  );
}

function ProjectListNoResults({ term, onClear }: { term: string; onClear: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-12 text-center">
      <p className="text-sm text-muted-foreground">No projects match “{term}”.</p>
      <Button variant="outline" onClick={onClear}>
        Clear search
      </Button>
    </div>
  );
}

function ProjectListError({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-lg border border-destructive/40 p-12 text-center"
    >
      <p className="text-sm text-destructive">We couldn’t load your projects.</p>
      <Button variant="outline" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

interface ProjectListViewProps {
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  total: number;
  searchTerm: string;
  visible: Project[];
  onCreate: () => void;
  onClearSearch: () => void;
  onOpen: (p: Project) => void;
  onRename: (p: Project) => void;
  onDelete: (p: Project) => void;
}

export function ProjectListView({
  isLoading,
  isError,
  onRetry,
  total,
  searchTerm,
  visible,
  onCreate,
  onClearSearch,
  onOpen,
  onRename,
  onDelete,
}: ProjectListViewProps) {
  if (isLoading) return <ProjectListSkeleton />;
  if (isError) return <ProjectListError onRetry={onRetry} />;
  if (total === 0) return <ProjectListEmpty onCreate={onCreate} />;
  if (visible.length === 0)
    return <ProjectListNoResults term={searchTerm} onClear={onClearSearch} />;

  const actions = { onOpen, onRename, onDelete };
  return (
    <>
      <div className="hidden md:block">
        <ProjectTable projects={visible} {...actions} />
      </div>
      <div className="md:hidden">
        <ProjectCardGrid projects={visible} {...actions} />
      </div>
    </>
  );
}
