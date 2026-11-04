/** The compatibility report of a project's Overleaf template import (spec 120). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getLatestImport, markImportReportSeen, type CompatFinding, type ProjectImport } from "./api";

export const templateReportKey = (projectId: string | undefined) => ["project", projectId, "import"] as const;

export interface TemplateReport {
  importId: string;
  findings: CompatFinding[];
  /** True until the person dismisses or opens the report once; the notice shows only then. */
  unseen: boolean;
  markSeen: () => void;
}

/** The findings of the latest import when it came from a template, else an empty report. */
export function useTemplateReport(projectId: string): TemplateReport {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: templateReportKey(projectId),
    queryFn: () => getLatestImport(projectId),
    staleTime: 60_000,
  });
  const row: ProjectImport | null = query.data ?? null;
  const template = row?.source === "overleaf_template" ? row : null;
  const seen = useMutation({
    mutationFn: (importId: string) => markImportReportSeen(projectId, importId),
    onSuccess: () =>
      qc.setQueryData<ProjectImport | null>(templateReportKey(projectId), (old) =>
        old ? { ...old, reportSeenAt: new Date().toISOString() } : old,
      ),
  });
  const importId = template?.importId ?? "";
  return {
    importId,
    findings: template?.compatReport ?? [],
    unseen: template !== null && template.reportSeenAt === null && (template.compatReport?.length ?? 0) > 0,
    markSeen: () => {
      if (template && template.reportSeenAt === null) seen.mutate(template.importId);
    },
  };
}
