import { useEffect, useState } from "react";
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
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type { TreeNode } from "./types";
import { validateEntityName } from "./validate-name";

export function CreateEntityDialog({
  open,
  onOpenChange,
  type,
  onCreate,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  type: "folder" | "doc";
  onCreate: (name: string) => void;
}) {
  const { t } = useTranslation("files");
  const [name, setName] = useState("");
  useEffect(() => {
    if (open)
      setName(
        type === "folder" ? t("createDialog.defaultFolderName") : t("createDialog.defaultFileName"),
      );
  }, [open, type, t]);

  const error = name ? validateEntityName(name) : t("validate.required");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!error) onCreate(name.trim());
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {type === "folder" ? t("createDialog.folderTitle") : t("createDialog.fileTitle")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3" noValidate>
          <div className="space-y-1">
            <label htmlFor="entity-name" className="text-sm font-medium">
              {t("createDialog.nameLabel")}
            </label>
            <Input
              id="entity-name"
              autoFocus
              value={name}
              aria-invalid={name && error ? true : undefined}
              onFocus={(e) => e.target.select()}
              onChange={(e) => setName(e.target.value)}
            />
            {name && error && (
              <p role="alert" className="text-xs text-destructive">
                {error}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!!error}>
              {t("common:action.create")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function DeleteEntityDialog({
  open,
  onOpenChange,
  node,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  node: TreeNode | null;
  onConfirm: () => void;
}) {
  const { t } = useTranslation("files");
  const isFolder = node?.type === "folder";
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("deleteDialog.title", { name: node?.name })}</AlertDialogTitle>
          <AlertDialogDescription>
            {isFolder ? t("deleteDialog.folderDescription") : t("deleteDialog.fileDescription")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("common:action.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            className={cn(buttonVariants({ variant: "destructive" }))}
            onClick={onConfirm}
          >
            {t("common:action.delete")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
