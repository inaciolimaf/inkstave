import { useEffect, useState } from "react";

export type OutputTab = "problems" | "log";

/** The compile output dock: which tab shows and whether the dock is collapsed. */
export function useOutputDock(errorOutcome: string | null) {
  const [tab, setTab] = useState<OutputTab>("problems");
  const [collapsed, setCollapsed] = useState(false);

  // Reveal the Log tab on a failed/timed-out/errored compile (§5.3.6); expand
  // the output dock too in case the user had collapsed it.
  useEffect(() => {
    if (errorOutcome) {
      setTab("log");
      setCollapsed(false);
    }
  }, [errorOutcome]);

  // Reveal a tab from elsewhere (e.g. the error state's "View log"): select it
  // and make sure the dock is expanded.
  const showTab = (next: OutputTab) => {
    setTab(next);
    setCollapsed(false);
  };

  return { tab, collapsed, showTab, toggleCollapsed: () => setCollapsed((c) => !c) };
}

export type OutputDock = ReturnType<typeof useOutputDock>;
