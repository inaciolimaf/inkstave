/** The scrolling content of the review dialog: its query states, the apply result, or the files. */
import { useTranslation } from "react-i18next";

import { QueryView } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";

import { ApplyResultAlert } from "./ApplyResultAlert";
import { FileSection } from "./FileSection";
import type { DiffProposal } from "./types";
import type { DiffReview } from "./useDiffReview";

function ProposalContent({ proposal, review: r }: { proposal: DiffProposal | null; review: DiffReview }) {
  const { t } = useTranslation("review");
  if (!proposal || proposal.files.length === 0) {
    return <p className="text-body text-muted-foreground">{t("noChanges")}</p>;
  }
  if (r.applyPhase === "error") {
    return (
      <ApplyResultAlert
        title={t("applyResult.errorTitle")}
        results={r.results ?? []}
        variant="destructive"
        role="alert"
      />
    );
  }
  if (r.applyPhase === "applied") {
    return <ApplyResultAlert title={t("applyResult.successTitle")} results={r.results ?? []} />;
  }
  return proposal.files.map((file) => (
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
  ));
}

export function ReviewBody({ review }: { review: DiffReview }) {
  const { t } = useTranslation("review");
  return (
    <div className="min-h-0 flex-1 divide-y divide-border-strong overflow-auto pr-1">
      <QueryView
        query={review.query}
        errorMessage={t("loadError")}
        loading={
          <div className="space-y-2" aria-busy="true">
            <Skeleton className="h-6" />
            <Skeleton className="h-32" />
          </div>
        }
      >
        {(proposal) => <ProposalContent proposal={proposal} review={review} />}
      </QueryView>
    </div>
  );
}
