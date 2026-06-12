export type EntityType = "folder" | "doc" | "file";

export interface TreeEntity {
  id: string;
  name: string;
  type: EntityType;
  parentId: string | null;
  isRoot: boolean;
  path: string;
}

/**
 * The normalised flat-map shape from spec 17 §5.1: a root id plus a flat list
 * of entities. The UI currently derives its nested `TreeNode` form directly, so
 * this interface documents the spec's data contract for normalised consumers.
 */
export interface ProjectTree {
  rootId: string;
  entities: TreeEntity[];
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
