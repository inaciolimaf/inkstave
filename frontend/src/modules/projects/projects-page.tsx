import { ChevronDown, Plus, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "@/modules/auth";
import { InkstaveLogo } from "@/components/inkstave-logo";
import { Manuscript, ManuscriptHeader, Rule } from "@/components/manuscript";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useDebouncedValue } from "@/lib/use-debounced-value";

import { ImportProjectDialog } from "./import-project-dialog";
import {
  CreateProjectDialog,
  DeleteProjectDialog,
  LeaveProjectDialog,
  RenameProjectDialog,
} from "./project-dialogs";
import { OverleafTemplateDialog } from "./overleaf-template-dialog";
import { ProjectListView } from "./project-list-view";
import { ProjectScopeControl } from "./project-scope-control";
import type { ListedProject, ProjectScope, SortKey } from "./types";
import { NotificationsBell } from "@/modules/notifications";

import { parseScope, useProjects, visibleProjects } from "./use-projects";

type DialogState = {
  type: "create" | "import" | "template" | "rename" | "delete" | "leave" | null;
  project?: ListedProject;
};

/** The projects dashboard header: title, search, sort, and new-project action (spec 16 §5.3.2). */
function ProjectsHeader({
  search,
  onSearchChange,
  sortKey,
  onSortChange,
  onCreate,
  onImport,
  onTemplate,
}: {
  search: string;
  onSearchChange: (value: string) => void;
  sortKey: SortKey;
  onSortChange: (value: SortKey) => void;
  onCreate: () => void;
  onImport: () => void;
  onTemplate: () => void;
}) {
  const { t } = useTranslation("projects");
  return (
    <>
      <ManuscriptHeader
        title={t("header.title")}
        actions={
          <>
            <Button variant="outline" onClick={onImport}>
              <Upload />
              {t("import.cta")}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button>
                  <Plus />
                  {t("header.newProject")}
                  <ChevronDown aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={onCreate}>{t("header.blankProject")}</DropdownMenuItem>
                <DropdownMenuItem onSelect={onTemplate}>{t("template.menuItem")}</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />
      <Rule />

      <div className="flex items-center gap-3 border-b border-border">
        <Input
          aria-label={t("header.searchLabel")}
          placeholder={t("header.searchPlaceholder")}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="min-w-0 flex-1 rounded-none border-0 bg-transparent px-0 shadow-none"
        />
        <Select value={sortKey} onValueChange={(v) => onSortChange(v as SortKey)}>
          <SelectTrigger
            aria-label={t("header.sortLabel")}
            className="w-auto shrink-0 gap-2 border-0 bg-transparent px-0 text-muted-foreground shadow-none"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="updatedAt">{t("header.sort.updatedAt")}</SelectItem>
            <SelectItem value="name">{t("header.sort.name")}</SelectItem>
            <SelectItem value="createdAt">{t("header.sort.createdAt")}</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </>
  );
}

export function ProjectsPage() {
  const { t } = useTranslation("projects");
  const projectsQuery = useProjects();
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  // The filter lives in `?scope=` so a reload keeps it (spec 109).
  const [params, setParams] = useSearchParams();
  const scope = parseScope(params.get("scope"));

  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, 150);
  const [sortKey, setSortKey] = useState<SortKey>("updatedAt");
  const [dialog, setDialog] = useState<DialogState>({ type: null });

  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);
  const visible = useMemo(
    () => visibleProjects(projects, debouncedSearch, sortKey, scope),
    [projects, debouncedSearch, sortKey, scope],
  );

  const onScopeChange = (next: ProjectScope) =>
    setParams(
      (prev) => {
        const updated = new URLSearchParams(prev);
        if (next === "all") updated.delete("scope");
        else updated.set("scope", next);
        return updated;
      },
      { replace: true },
    );

  const closeDialog = (open: boolean) => {
    if (!open) setDialog({ type: null });
  };

  const onLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <Manuscript
      bar={
        <div className="flex items-center justify-between px-4 py-3 sm:px-6">
          <InkstaveLogo />
          <div className="flex items-center gap-1">
            <NotificationsBell />
            <Button variant="ghost" size="sm" onClick={() => navigate("/settings")}>
              {t("nav.settings")}
            </Button>
            <Button variant="ghost" size="sm" onClick={onLogout}>
              {t("common:action.signOut")}
            </Button>
          </div>
        </div>
      }
    >
      <ProjectsHeader
        search={search}
        onSearchChange={setSearch}
        sortKey={sortKey}
        onSortChange={setSortKey}
        onCreate={() => setDialog({ type: "create" })}
        onImport={() => setDialog({ type: "import" })}
        onTemplate={() => setDialog({ type: "template" })}
      />

      <ProjectScopeControl value={scope} onChange={onScopeChange} />

      <ProjectListView
        query={projectsQuery}
        searchTerm={debouncedSearch}
        scope={scope}
        visible={visible}
        onCreate={() => setDialog({ type: "create" })}
        onClearSearch={() => setSearch("")}
        onOpen={(p) => navigate(`/projects/${p.id}`)}
        onRename={(p) => setDialog({ type: "rename", project: p })}
        onDelete={(p) => setDialog({ type: "delete", project: p })}
        onLeave={(p) => setDialog({ type: "leave", project: p })}
      />

      <CreateProjectDialog open={dialog.type === "create"} onOpenChange={closeDialog} />
      <LeaveProjectDialog
        open={dialog.type === "leave"}
        onOpenChange={closeDialog}
        project={dialog.project ?? null}
        userId={user?.id ?? null}
      />
      <ImportProjectDialog open={dialog.type === "import"} onOpenChange={closeDialog} />
      <OverleafTemplateDialog open={dialog.type === "template"} onOpenChange={closeDialog} />
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
    </Manuscript>
  );
}
