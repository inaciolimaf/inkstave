import type { EditorKeymap } from "@/types";

/** Document text + optimistic-concurrency version (mirrors spec 13/18 §5.1). */
export interface DocumentContent {
  id: string;
  /**
   * The document's display name (spec 18 §5.1). The backend
   * `DocumentContentRead` wire currently omits it, so it is optional and sourced
   * from the tree entity when available. (Backend gap reported by spec 73.)
   */
  name?: string;
  content: string;
  version: number;
}

export interface EditorSettings {
  fontSize: number;
  /** default | vim | emacs (spec 59; persisted server-side). */
  keymap: EditorKeymap;
  lineWrapping: boolean;
}
