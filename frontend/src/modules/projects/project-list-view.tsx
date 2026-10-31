import type { UseQueryResult } from "@tanstack/react-query";
import { FolderPlus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { ProjectIndex } from "./project-index";
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
    <div className="flex flex-col items-start gap-4 py-12">
      <FolderPlus className="size-10 text-muted-foreground" />
      <div>
        <p className="font-medium">{t("list.emptyTitle")}</p>
        <p className="text-body text-muted-foreground">{t("list.emptyDescription")}</p>
      </div>
      <Button onClick={onCreate}>{t("list.createFirst")}</Button>
    </div>
  );
}

function ProjectListNoResults({ term, onClear }: { term: string; onClear: () => void }) {
  const { t } = useTranslation("projects");
  return (
    <div className="flex flex-col items-start gap-3 py-12">
      <p className="text-body text-muted-foreground">{t("list.noResults", { term })}</p>
      <Button variant="outline" onClick={onClear}>
        {t("list.clearSearch")}
      </Button>
    </div>
  );
}

interface ProjectListViewProps {
  query: Pick<UseQueryResult<Project[]>, "data" | "isLoading" | "isError" | "refetch">;
  searchTerm: string;
  visible: Project[];
  onCreate: () => void;
  onClearSearch: () => void;
  onOpen: (p: Project) => void;
  onRename: (p: Project) => void;
  onDelete: (p: Project) => void;
}

export function ProjectListView({
  query,
  searchTerm,
  visible,
  onCreate,
  onClearSearch,
  onOpen,
  onRename,
  onDelete,
}: ProjectListViewProps) {
  const { t } = useTranslation("projects");
  return (
    <QueryView
      query={query}
      loading={<ProjectListSkeleton />}
      errorMessage={t("list.loadError")}
      errorClassName="flex-col items-start gap-3 py-12"
    >
      {(projects) => {
        if (projects.length === 0) return <ProjectListEmpty onCreate={onCreate} />;
        if (visible.length === 0) return <ProjectListNoResults term={searchTerm} onClear={onClearSearch} />;
        return <ProjectIndex projects={visible} onOpen={onOpen} onRename={onRename} onDelete={onDelete} />;
      }}
    </QueryView>
  );
}
