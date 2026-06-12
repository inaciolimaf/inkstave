/** Confirmation AlertDialogs for the diff-review surface: apply + discard (spec 47). */
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
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Apply changes?</AlertDialogTitle>
          <AlertDialogDescription>
            This will write {plan.applicable} accepted change
            {plan.applicable === 1 ? "" : "s"} across {plan.fileCount} file
            {plan.fileCount === 1 ? "" : "s"} into your document
            {plan.fileCount === 1 ? "" : "s"}.
            {plan.blocked > 0 &&
              ` ${plan.blocked} hunk${plan.blocked === 1 ? "" : "s"} no longer apply and will be skipped.`}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              onConfirm();
            }}
          >
            Apply
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
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Discard your review?</AlertDialogTitle>
          <AlertDialogDescription>
            Your accept/reject choices will be lost.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep reviewing</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Discard</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
