import { useEffect, useState } from "react";

export type OutputTab = "problems" | "log";

/** The compile output dock: which tab shows and whether the dock is collapsed. */
export function useOutputDock(errorOutcome: string | null, floating = false) {
  const [tab, setTab] = useState<OutputTab>("problems");
  // A floating dock (spec 107) covers the text, so it only opens when there is something to act on.
  const [collapsed, setCollapsed] = useState(floating);

  // Reveal the output on a failed/timed-out/errored compile (§5.3.6); expand the dock too in case the
  // user had collapsed it. The floating dock leads with the problems, the docked one with the log.
  useEffect(() => {
    if (errorOutcome) {
      setTab(floating ? "problems" : "log");
      setCollapsed(false);
    }
  }, [errorOutcome, floating]);

  // Reveal a tab from elsewhere (e.g. the error state's "View log"): select it
  // and make sure the dock is expanded.
  const showTab = (next: OutputTab) => {
    setTab(next);
    setCollapsed(false);
  };

  return { tab, collapsed, showTab, toggleCollapsed: () => setCollapsed((c) => !c) };
}

export type OutputDock = ReturnType<typeof useOutputDock>;
