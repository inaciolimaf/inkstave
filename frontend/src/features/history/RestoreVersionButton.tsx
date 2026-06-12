/** Restore-with-confirmation for a selected version (spec 38). */
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import type { useHistoryMutations } from "./useHistory";

type RestoreMutation = ReturnType<typeof useHistoryMutations>["restore"];

export function RestoreVersionButton({
  version,
  restore,
}: {
  version: number;
  restore: RestoreMutation;
}) {
  const [open, setOpen] = useState(false);
  const [labelName, setLabelName] = useState("");

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="outline">
          Restore this version
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Restore version {version}?</AlertDialogTitle>
          <AlertDialogDescription>
            The document’s current content will be replaced with version {version}. A new version is
            created — nothing is deleted, and you can restore back at any time.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <Input
          value={labelName}
          onChange={(e) => setLabelName(e.target.value)}
          placeholder="Add a label for this restore (optional)"
          aria-label="Restore label"
        />
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={restore.isPending}
            onClick={(e) => {
              e.preventDefault(); // keep the dialog open unless the restore succeeds
              restore.mutate(
                { version, labelName: labelName.trim() || undefined },
                {
                  onSuccess: (result) => {
                    toast.success(
                      `Restored to version ${version}; created version ${result.newVersion}.`,
                    );
                    setLabelName("");
                    setOpen(false);
                  },
                  onError: () => toast.error("Restore failed. Please try again."),
                },
              );
            }}
          >
            {restore.isPending ? "Restoring…" : "Restore"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
