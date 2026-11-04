/** The editor's wiring for the template compatibility report (spec 120). */
import { useState } from "react";
import { createPortal } from "react-dom";

import { useTemplateReport } from "@/modules/projects";

import { CompatNotice, CompatReportDialog } from "./compat-notice";

/**
 * The report's wiring for the editor screen: the menu entry (only for a template with findings), the
 * notice in the status line until it is seen, and the list. The caller renders `element` once.
 */
export function useCompatReport(
  projectId: string,
  statusSlot: HTMLElement | null,
  onOpenLine: (path: string, line: number) => void,
) {
  const report = useTemplateReport(projectId);
  const [open, setOpen] = useState(false);
  const openReport = () => {
    report.markSeen();
    setOpen(true);
  };
  const notice =
    statusSlot && report.unseen
      ? createPortal(
          <CompatNotice count={report.findings.length} onReview={openReport} onDismiss={report.markSeen} />,
          statusSlot,
        )
      : null;
  return {
    menu: { onOpenCompatReport: report.findings.length > 0 ? () => setOpen(true) : undefined },
    element: (
      <>
        {notice}
        <CompatReportDialog
          open={open}
          onOpenChange={setOpen}
          findings={report.findings}
          onOpenLine={onOpenLine}
        />
      </>
    ),
  };
}
