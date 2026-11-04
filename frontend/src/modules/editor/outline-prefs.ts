/**
 * What the writer last chose for the drawer: its tab (Files, Outline, Search: specs 111 and 122), and whether the
 * outline is pinned beside the text.
 */
import { useCallback, useState } from "react";

export type DrawerTab = "files" | "outline" | "search";

const TABS: readonly DrawerTab[] = ["files", "outline", "search"];

const TAB_KEY = "inkstave:drawer-tab";
const PINNED_KEY = "inkstave:outline-pinned";

/** localStorage can be blocked or full; the choice then lasts only for the page. */
function readFlag(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeFlag(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* not remembered; the state still works */
  }
}

export function useDrawerTab(): [DrawerTab, (tab: DrawerTab) => void] {
  const [tab, setTabState] = useState<DrawerTab>(() => {
    const saved = readFlag(TAB_KEY);
    return TABS.find((name) => name === saved) ?? "files";
  });
  const setTab = useCallback((next: DrawerTab) => {
    writeFlag(TAB_KEY, next);
    setTabState(next);
  }, []);
  return [tab, setTab];
}

export function useOutlinePinned(): [boolean, () => void] {
  const [pinned, setPinned] = useState(() => readFlag(PINNED_KEY) === "true");
  const toggle = () => {
    writeFlag(PINNED_KEY, String(!pinned));
    setPinned(!pinned);
  };
  return [pinned, toggle];
}
