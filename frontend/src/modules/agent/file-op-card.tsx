/** A file operation the agent proposed: nothing happens until the user applies it here. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FilePlus, FolderPlus, MoveRight, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import { treeKey } from "@/modules/file-tree";

import { decideFileOp, fetchFileOpContent } from "./api";
import type { FileOp } from "./types";

const HAND = "min-w-0 space-y-2 border-l-2 border-primary pl-3";

function opLabel(op: FileOp) {
  if (op.opKind === "delete") return "transcript.fileOp.delete";
  if (op.opKind === "move") return "transcript.fileOp.move";
  return op.entityType === "folder" ? "transcript.fileOp.createFolder" : "transcript.fileOp.createDoc";
}

function OpIcon({ op }: { op: FileOp }) {
  const className = "size-4 text-primary";
  if (op.opKind === "delete") return <Trash2 className={className} aria-hidden="true" />;
  if (op.opKind === "move") return <MoveRight className={className} aria-hidden="true" />;
  if (op.entityType === "folder") return <FolderPlus className={className} aria-hidden="true" />;
  return <FilePlus className={className} aria-hidden="true" />;
}

function ContentPreview({
  projectId,
  sessionId,
  opId,
}: {
  projectId: string;
  sessionId: string;
  opId: string;
}) {
  const { t } = useTranslation("agent");
  const query = useQuery({
    queryKey: ["agent-file-op-content", opId],
    queryFn: () => fetchFileOpContent(projectId, sessionId, opId),
  });
  if (query.isLoading)
    return <Skeleton className="h-16" aria-label={t("transcript.fileOp.loadingContent")} />;
  return (
    <pre className="max-h-48 overflow-auto border-y py-1.5 font-mono text-small">
      <code>{query.data}</code>
    </pre>
  );
}

function DeleteConfirm({
  open,
  path,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  path: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation("agent");
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="break-all">
            {t("transcript.fileOp.confirmDeleteTitle", { path })}
          </AlertDialogTitle>
          <AlertDialogDescription>{t("transcript.fileOp.confirmDeleteDescription")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("transcript.fileOp.cancel")}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{t("transcript.fileOp.confirmDelete")}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function useFileOpDecision(projectId: string, sessionId: string, op: FileOp) {
  const { t } = useTranslation("agent");
  const qc = useQueryClient();
  const [status, setStatus] = useState(op.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decide = async (decision: "apply" | "reject") => {
    setBusy(true);
    setError(null);
    try {
      const updated = await decideFileOp(projectId, sessionId, op.opId, decision);
      setStatus(updated.status);
      if (decision === "apply") await qc.invalidateQueries({ queryKey: treeKey(projectId) });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("transcript.fileOp.failed"));
    } finally {
      setBusy(false);
    }
  };
  return { status, busy, error, decide };
}

export function FileOpCard({
  projectId,
  sessionId,
  op,
}: {
  projectId: string;
  sessionId: string;
  op: FileOp;
}) {
  const { t } = useTranslation("agent");
  const { status, busy, error, decide } = useFileOpDecision(projectId, sessionId, op);
  const [showContent, setShowContent] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const inside = op.affectedPaths.filter((path) => path !== op.path);
  const hasContent = op.opKind === "create" && op.entityType === "doc";
  return (
    <div className={HAND}>
      <div className="flex items-center gap-2 text-body font-medium">
        <OpIcon op={op} />
        {t(opLabel(op))}
      </div>
      <p className="break-all font-mono text-small text-muted-foreground">
        {op.newPath ? `${op.path} → ${op.newPath}` : op.path}
      </p>
      {op.rationale && <p className="text-small text-muted-foreground">{op.rationale}</p>}
      {inside.length > 0 && (
        <p className="text-small text-error-text">
          {t("transcript.fileOp.alsoDeletes", { count: inside.length })}
        </p>
      )}
      {showContent && <ContentPreview projectId={projectId} sessionId={sessionId} opId={op.opId} />}
      {status === "proposed" ? (
        <div className="flex flex-wrap gap-1">
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => (op.opKind === "delete" ? setConfirming(true) : void decide("apply"))}
          >
            {t("transcript.fileOp.apply")}
          </Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void decide("reject")}>
            {t("transcript.fileOp.reject")}
          </Button>
          {hasContent && (
            <Button size="sm" variant="ghost" onClick={() => setShowContent((shown) => !shown)}>
              {t(showContent ? "transcript.fileOp.hideContent" : "transcript.fileOp.showContent")}
            </Button>
          )}
        </div>
      ) : (
        <p className="text-small text-muted-foreground" role="status">
          {t(status === "applied" ? "transcript.fileOp.applied" : "transcript.fileOp.rejected")}
        </p>
      )}
      {error && (
        <p className="text-small text-error-text" role="alert">
          {error}
        </p>
      )}
      <DeleteConfirm
        open={confirming}
        path={op.path}
        onOpenChange={setConfirming}
        onConfirm={() => void decide("apply")}
      />
    </div>
  );
}
