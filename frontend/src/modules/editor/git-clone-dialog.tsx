import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { gitCloneUrl } from "./git-url";

function CopyRow({ label, value }: { label: string; value: string }) {
  const { t } = useTranslation("editor");
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-1">
      <p className="text-small text-muted-foreground">{label}</p>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 break-all rounded bg-muted px-2 py-1 font-mono text-small">
          {value}
        </code>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            void navigator.clipboard?.writeText(value);
            setCopied(true);
          }}
        >
          {copied ? t("git.copied") : t("git.copy")}
        </Button>
      </div>
    </div>
  );
}

/** Editor → More → Git (spec 121): the clone address and the command for it. */
export function GitCloneDialog({
  projectId,
  open,
  onOpenChange,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation("editor");
  const url = gitCloneUrl(projectId);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("git.title")}</DialogTitle>
          <DialogDescription>{t("git.description")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <CopyRow label={t("git.cloneUrl")} value={url} />
          <CopyRow label={t("git.command")} value={`git clone ${url}`} />
          <p className="text-small text-muted-foreground">
            {t("git.passwordNote")}{" "}
            <Link to="/settings" className="underline" onClick={() => onOpenChange(false)}>
              {t("git.manageTokens")}
            </Link>
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
