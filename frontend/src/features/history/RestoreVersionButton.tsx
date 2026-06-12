/** Restore-with-confirmation for a selected version (spec 38). */
import { useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("history");
  const [open, setOpen] = useState(false);
  const [labelName, setLabelName] = useState("");

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="outline">
          {t("restore.trigger")}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("restore.confirmTitle", { version })}</AlertDialogTitle>
          <AlertDialogDescription>
            {t("restore.confirmDescription", { version })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <Input
          value={labelName}
          onChange={(e) => setLabelName(e.target.value)}
          placeholder={t("restore.labelPlaceholder")}
          aria-label={t("restore.labelAriaLabel")}
        />
        <AlertDialogFooter>
          <AlertDialogCancel>{t("restore.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            disabled={restore.isPending}
            onClick={(e) => {
              e.preventDefault(); // keep the dialog open unless the restore succeeds
              restore.mutate(
                { version, labelName: labelName.trim() || undefined },
                {
                  onSuccess: (result) => {
                    toast.success(
                      t("restore.success", { version, newVersion: result.newVersion }),
                    );
                    setLabelName("");
                    setOpen(false);
                  },
                  onError: () => toast.error(t("restore.error")),
                },
              );
            }}
          >
            {restore.isPending ? t("restore.restoring") : t("restore.action")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
