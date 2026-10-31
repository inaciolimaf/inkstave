import type { ReactNode } from "react";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { cn } from "@/lib/utils";

import type { MobileView } from "./mobile-tabs";

/** The text and the PDF: side by side and always there, or one at a time on a phone (spec 107). */
export function Panes({
  projectId,
  wide,
  view,
  content,
  preview,
}: {
  projectId: string;
  wide: boolean;
  view: MobileView;
  content: ReactNode;
  preview: ReactNode;
}) {
  if (!wide) {
    // Both stay mounted: a compile, the PDF's page and the cursor survive the switch.
    return (
      <div className="min-h-0 flex-1">
        <div className={cn("h-full", view !== "content" && "hidden")}>{content}</div>
        <div className={cn("h-full", view !== "preview" && "hidden")}>{preview}</div>
      </div>
    );
  }
  return (
    <ResizablePanelGroup
      direction="horizontal"
      autoSaveId={`inkstave:split:${projectId}`}
      className="min-h-0 flex-1"
    >
      <ResizablePanel defaultSize={52} minSize={25} className="min-h-0">
        {content}
      </ResizablePanel>
      <ResizableHandle />
      <ResizablePanel defaultSize={48} minSize={20} className="min-h-0">
        {preview}
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
