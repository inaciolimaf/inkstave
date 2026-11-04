/** The agent's proposals reviewed in the open text (spec 110): the review, its bar, and the outcomes it reports. */
import { useState } from "react";

import { ReviewBar, useInlineReview } from "@/modules/diff-review";
import type { TreeEntity, TreeNode } from "@/modules/file-tree";

import type { MobileView } from "./mobile-tabs";
import { findNodeByPath } from "./sync-decoration";
import { useDocumentBridge } from "./use-document-bridge";
import type { useSourceSync } from "./use-source-sync";

export function useProposalReview({
  projectId,
  sync,
  treeRoot,
  readOnly,
  wide,
  setSelected,
  setView,
}: {
  projectId: string;
  sync: ReturnType<typeof useSourceSync>;
  treeRoot: TreeNode | undefined;
  readOnly: boolean;
  wide: boolean;
  setSelected: (entity: TreeEntity) => void;
  setView: (view: MobileView) => void;
}) {
  const [proposalStatuses, setProposalStatuses] = useState<Record<string, string>>({});
  const bridge = useDocumentBridge(projectId, treeRoot);

  // A proposal opens in its document, switching the editor to it first, as a jump to a source line does.
  const openProposalDocument = (path: string): boolean => {
    if (sync.openDoc?.path === path) return true;
    const node = treeRoot ? findNodeByPath(treeRoot, path) : null;
    if (!node || node.type !== "doc") return false;
    if (!wide) setView("content");
    setSelected(node);
    return true;
  };

  const review = useInlineReview({
    projectId,
    bridge,
    view: sync.editorView,
    openPath: sync.openDoc?.path ?? null,
    canDecide: !readOnly,
    openDocument: openProposalDocument,
    onDecided: (proposalId, status) => setProposalStatuses((s) => ({ ...s, [proposalId]: status })),
  });

  return {
    open: review.open,
    proposalStatuses,
    reviewBar: review.bar ? <ReviewBar {...review.bar} /> : null,
  };
}
