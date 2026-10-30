/** Confirmation AlertDialogs for the diff-review surface: apply + discard (spec 47). */
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

/** Confirms writing the accepted hunks into the live document(s). */
export function ApplyConfirmDialog({
  open,
  onOpenChange,
  plan,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  plan: { fileCount: number; applicable: number; blocked: number };
  onConfirm: () => void;
}) {
  const { t } = useTranslation("review");
  const { t: tCommon } = useTranslation("common");
  const manyChanges = plan.applicable !== 1;
  const manyFiles = plan.fileCount !== 1;
  const descriptionKey = manyChanges
    ? manyFiles
      ? "confirmApply.descriptionMany_fileMany"
      : "confirmApply.descriptionMany"
    : manyFiles
      ? "confirmApply.description_fileMany"
      : "confirmApply.description";
  const blockedText =
    plan.blocked > 0
      ? t(plan.blocked === 1 ? "confirmApply.blocked" : "confirmApply.blockedMany", {
          count: plan.blocked,
        })
      : "";
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("confirmApply.title")}</AlertDialogTitle>
          <AlertDialogDescription>
            {t(descriptionKey, { applicable: plan.applicable, fileCount: plan.fileCount })}
            {blockedText}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{tCommon("action.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              onConfirm();
            }}
          >
            {t("confirmApply.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** Guards dismissal when the user has pending accept/reject decisions. */
export function DiscardConfirmDialog({
  open,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation("review");
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("confirmDiscard.title")}</AlertDialogTitle>
          <AlertDialogDescription>{t("confirmDiscard.description")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("confirmDiscard.keep")}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{t("confirmDiscard.discard")}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
