/** The diff-review surface: per-file diff, per-hunk accept/reject, preview, apply (spec 47). */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

import { ApplyResultAlert } from "./ApplyResultAlert";
import { ApplyConfirmDialog, DiscardConfirmDialog } from "./ConfirmDialogs";
import { FileSection } from "./FileSection";
import type { DocumentBridge } from "./types";
import { useDiffReview } from "./useDiffReview";

export function DiffReviewDialog({
  projectId,
  sessionId,
  proposalId,
  bridge,
  open,
  onOpenChange,
}: {
  projectId: string;
  sessionId: string;
  proposalId: string | null;
  bridge: DocumentBridge;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation("review");
  const { t: tCommon } = useTranslation("common");
  const r = useDiffReview(projectId, sessionId, proposalId, bridge, open);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  // Pending = a loaded proposal with reviewable hunks that hasn't been applied
  // yet. Dismissing in this state would silently drop the user's accept/reject
  // choices, so we guard it (#191).
  const hasPendingDecisions =
    !!r.proposal &&
    r.proposal.files.length > 0 &&
    r.counts.total > 0 &&
    r.applyPhase !== "applied" &&
    r.applyPhase !== "applying";

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      if (hasPendingDecisions) {
        setConfirmDiscard(true);
      } else {
        onOpenChange(false);
      }
      return;
    }
    onOpenChange(true);
  };

  const onApply = async () => {
    const outcome = await r.apply();
    if (outcome.phase === "error") {
      toast.error(t("toast.applyError"));
    } else {
      toast.success(t("toast.applySuccess"));
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="flex max-h-[85vh] max-w-3xl flex-col gap-3"
        onInteractOutside={(e) => {
          // Ignore interactions that originate inside a nested confirmation
          // dialog (the apply-confirm / discard AlertDialogs portal *outside*
          // this content, so Radix reports them as "outside" interactions).
          const target = e.target as Element | null;
          if (target?.closest('[role="alertdialog"]')) return;
          if (hasPendingDecisions) {
            e.preventDefault();
            setConfirmDiscard(true);
          }
        }}
        onEscapeKeyDown={(e) => {
          // Escape while a nested confirmation dialog is open belongs to that
          // dialog, not to dismissing the review surface.
          if (r.applyPhase === "confirming" || confirmDiscard) return;
          if (hasPendingDecisions) {
            e.preventDefault();
            setConfirmDiscard(true);
          }
        }}
      >
        <DialogDescription className="sr-only">{t("description")}</DialogDescription>
        <DialogHeader className="flex-row items-center justify-between gap-2 space-y-0">
          <DialogTitle>{t("title")}</DialogTitle>
          <div className="flex items-center gap-2 pr-6">
            <span className="text-sm text-muted-foreground">
              {t("accepted", { accepted: r.counts.accepted, total: r.counts.total })}
            </span>
            <Button
              size="sm"
              disabled={r.applyPhase === "applying" || r.counts.total === 0}
              onClick={() => r.setApplyPhase("confirming")}
            >
              {t("apply")}
            </Button>
          </div>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-4 overflow-auto">
          {r.loading ? (
            <div className="space-y-2" aria-busy="true">
              <Skeleton className="h-6" />
              <Skeleton className="h-32" />
            </div>
          ) : r.isError ? (
            <div className="flex items-center gap-2 text-sm text-destructive" role="alert">
              {t("loadError")}
              <Button size="sm" variant="outline" onClick={() => void r.refetch()}>
                {tCommon("action.retry")}
              </Button>
            </div>
          ) : !r.proposal || r.proposal.files.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noChanges")}</p>
          ) : r.applyPhase === "error" ? (
            <ApplyResultAlert
              title={t("applyResult.errorTitle")}
              results={r.results ?? []}
              variant="destructive"
              role="alert"
            />
          ) : r.applyPhase === "applied" ? (
            <ApplyResultAlert title={t("applyResult.successTitle")} results={r.results ?? []} />
          ) : (
            r.proposal.files.map((file) => (
              <FileSection
                key={file.path}
                file={file}
                decisions={r.decisions[file.path] ?? {}}
                blockedIds={r.files[file.path]?.blockedHunkIds ?? []}
                baseChanged={r.files[file.path]?.baseChanged ?? false}
                onToggle={(hunkId) => r.toggleHunk(file.path, hunkId)}
                onSetAll={(accepted) => r.setAll(file.path, accepted)}
                previewText={r.preview(file.path)}
              />
            ))
          )}
        </div>
      </DialogContent>

      <ApplyConfirmDialog
        open={r.applyPhase === "confirming"}
        onOpenChange={(o) => !o && r.setApplyPhase("idle")}
        plan={r.plan}
        onConfirm={() => void onApply()}
      />

      <DiscardConfirmDialog
        open={confirmDiscard}
        onOpenChange={setConfirmDiscard}
        onConfirm={() => {
          setConfirmDiscard(false);
          onOpenChange(false);
        }}
      />
    </Dialog>
  );
}
