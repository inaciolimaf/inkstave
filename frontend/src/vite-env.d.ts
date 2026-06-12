/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_COMPILE_POLL_INTERVAL_MS?: string;
  readonly VITE_COLLAB_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
