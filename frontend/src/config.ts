/** Runtime configuration read from Vite env (build-time inlined). */
export const config = {
  /** Backend origin/base for the API client. */
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
};
