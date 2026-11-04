import { useQuery } from "@tanstack/react-query";
import type { Dispatch, SetStateAction } from "react";

import type { TreeEntity, TreeNode } from "@/modules/file-tree";
import { getProject, projectKey } from "@/modules/projects";
import { isReadOnly, usePermissions } from "@/modules/sharing";

import { useSelectionFollowsTree } from "./selection-follows-tree";
import { useStartDocument } from "./start-document";

/** The project the workspace shows: its record, whether this user may only read it, and the selection rules. */
export function useWorkspaceProject(
  projectId: string,
  treeRoot: TreeNode | undefined,
  selected: TreeEntity | null,
  setSelected: Dispatch<SetStateAction<TreeEntity | null>>,
) {
  const permissions = usePermissions(projectId);
  const projectQuery = useQuery({
    queryKey: projectKey(projectId),
    queryFn: () => getProject(projectId),
  });
  useStartDocument(treeRoot, projectQuery.data?.rootDocId, selected, setSelected);
  useSelectionFollowsTree(treeRoot, selected, setSelected);
  return { projectQuery, readOnly: isReadOnly(permissions.data) };
}
