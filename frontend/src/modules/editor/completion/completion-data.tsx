import { type ReactNode, useRef } from "react";

import { CompletionDataContext } from "./completion-context";
import type { CompletionData } from "./types";

/**
 * Gives the editor the project data for completion (spec 112) through a ref, so the CodeMirror view, which is
 * created once, always reads the labels, citations and files of the latest render.
 */
export function CompletionDataProvider({ value, children }: { value: CompletionData; children: ReactNode }) {
  const ref = useRef(value);
  ref.current = value;
  return <CompletionDataContext.Provider value={ref}>{children}</CompletionDataContext.Provider>;
}
