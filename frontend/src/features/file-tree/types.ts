export type EntityType = "folder" | "doc" | "file";

export interface TreeEntity {
  id: string;
  name: string;
  type: EntityType;
  parentId: string | null;
  isRoot: boolean;
  path: string;
}

/** A folder/doc/file node; `children` is `[]` for non-folders. */
export interface TreeNode extends TreeEntity {
  children: TreeNode[];
}

/** A node flattened for keyboard navigation, carrying its depth + ancestry. */
export interface FlatNode {
  node: TreeNode;
  depth: number;
  parentId: string | null;
}
