import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>This document changed on the server</DialogTitle>
          <DialogDescription>
            Someone (or another tab) saved a newer version since you opened it. Choose how to
            resolve the conflict.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          {/* Default focus stays on the non-destructive "keep mine"; reloading discards local edits. */}
          <Button autoFocus onClick={onKeepMine}>
            Keep my version
          </Button>
          <Button variant="outline" onClick={onReload}>
            Reload server version
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
