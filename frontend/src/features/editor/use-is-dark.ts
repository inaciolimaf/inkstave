import { useEffect, useState } from "react";

const QUERY = "(prefers-color-scheme: dark)";

/** Tracks the OS-level dark-mode preference (`prefers-color-scheme`). This is the
 * signal used to resolve the "system" theme setting (spec 59); the resolved
 * theme is then applied to <html> by `useApplyTheme`. */
export function useIsDark(): boolean {
  const [dark, setDark] = useState(() => window.matchMedia(QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(QUERY);
    const update = () => setDark(mq.matches);
    mq.addEventListener("change", update);
    update();
    return () => mq.removeEventListener("change", update);
  }, []);
  return dark;
}
