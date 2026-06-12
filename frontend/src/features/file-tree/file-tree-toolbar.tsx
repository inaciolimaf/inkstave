import { FilePlus, FolderPlus, Upload } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

/** The "Files" header with the New file / New folder / Upload actions. */
export function FileTreeToolbar({
  readOnly,
  hasRoot,
  onNewDoc,
  onNewFolder,
  onUpload,
}: {
  readOnly: boolean;
  hasRoot: boolean;
  onNewDoc: () => void;
  onNewFolder: () => void;
  onUpload: () => void;
}) {
  const { t } = useTranslation("files");
  const actions = [
    { icon: FilePlus, label: t("action.newFile"), run: onNewDoc },
    { icon: FolderPlus, label: t("action.newFolder"), run: onNewFolder },
    { icon: Upload, label: t("action.uploadFile"), run: onUpload },
  ];
  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex items-center gap-1 border-b px-2 py-1">
        <span className="mr-auto text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("heading")}
        </span>
        {!readOnly &&
          actions.map(({ icon: Icon, label, run }) => (
            <Tooltip key={label}>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={label}
                  disabled={!hasRoot}
                  onClick={run}
                >
                  <Icon className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{label}</TooltipContent>
            </Tooltip>
          ))}
      </div>
    </TooltipProvider>
  );
}
