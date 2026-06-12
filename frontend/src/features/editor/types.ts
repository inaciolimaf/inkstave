/** Document text + optimistic-concurrency version (mirrors spec 13). */
export interface DocumentContent {
  id: string;
  content: string;
  version: number;
}

export interface EditorSettings {
  fontSize: number;
  /** Only the default keymap ships in this spec (see docs/adr/0018). */
  keymap: "default";
  lineWrapping: boolean;
}
