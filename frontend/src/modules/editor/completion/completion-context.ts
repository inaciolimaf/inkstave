import { createContext, useContext, type RefObject } from "react";

import { EMPTY_COMPLETION_DATA, type CompletionData } from "./types";

/** The project data for completion (spec 112), read through a ref by the editor's extensions. */
export const CompletionDataContext = createContext<RefObject<CompletionData>>({
  current: EMPTY_COMPLETION_DATA,
});

export function useCompletionData(): RefObject<CompletionData> {
  return useContext(CompletionDataContext);
}
