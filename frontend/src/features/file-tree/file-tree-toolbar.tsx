import { FilePlus, FolderPlus, Upload } from "lucide-react";

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
  const actions = [
    { icon: FilePlus, label: "New file", run: onNewDoc },
    { icon: FolderPlus, label: "New folder", run: onNewFolder },
    { icon: Upload, label: "Upload file", run: onUpload },
  ];
  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex items-center gap-1 border-b px-2 py-1">
        <span className="mr-auto text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Files
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
