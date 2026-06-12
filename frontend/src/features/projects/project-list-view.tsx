import { FolderPlus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { ProjectCardGrid, ProjectTable } from "./project-table";
import type { Project } from "./types";

function ProjectListSkeleton() {
  const { t } = useTranslation("projects");
  return (
    <div className="space-y-3" aria-busy="true" aria-label={t("list.loadingLabel")}>
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

function ProjectListEmpty({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation("projects");
  return (
    <div className="flex flex-col items-center gap-4 rounded-lg border border-dashed p-12 text-center">
      <FolderPlus className="size-10 text-muted-foreground" />
      <div>
        <p className="font-medium">{t("list.emptyTitle")}</p>
        <p className="text-sm text-muted-foreground">{t("list.emptyDescription")}</p>
      </div>
      <Button onClick={onCreate}>{t("list.createFirst")}</Button>
    </div>
  );
}

function ProjectListNoResults({ term, onClear }: { term: string; onClear: () => void }) {
  const { t } = useTranslation("projects");
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-12 text-center">
      <p className="text-sm text-muted-foreground">{t("list.noResults", { term })}</p>
      <Button variant="outline" onClick={onClear}>
        {t("list.clearSearch")}
      </Button>
    </div>
  );
}

function ProjectListError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation("projects");
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-lg border border-destructive/40 p-12 text-center"
    >
      <p className="text-sm text-destructive">{t("list.loadError")}</p>
      <Button variant="outline" onClick={onRetry}>
        {t("common:action.retry")}
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
