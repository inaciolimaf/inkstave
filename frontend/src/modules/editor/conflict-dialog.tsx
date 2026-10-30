import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

export function ConflictDialog({
  open,
  onOpenChange,
  onReload,
  onKeepMine,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onReload: () => void;
  onKeepMine: () => void;
}) {
  const { t } = useTranslation("editor");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("conflict.title")}</DialogTitle>
          <DialogDescription>{t("conflict.description")}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          {/* Default focus stays on the non-destructive "keep mine"; reloading discards local edits. */}
          <Button autoFocus onClick={onKeepMine}>
            {t("conflict.keepMine")}
          </Button>
          <Button variant="outline" onClick={onReload}>
            {t("conflict.reload")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
