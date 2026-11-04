/** The module's public interface: other modules and routes import only from here. */
export { createEditorBridge } from "./editor-bridge";
export { inlineReviewExtension } from "./inline-review-extension";
export { ReviewBar } from "./review-bar";
export type { ReviewBarProps } from "./review-bar";
export { useInlineReview } from "./use-inline-review";
export type { ProposalRef } from "./use-inline-review";
export type { DocumentBridge, LiveTextBridge, TextSplice } from "./types";
