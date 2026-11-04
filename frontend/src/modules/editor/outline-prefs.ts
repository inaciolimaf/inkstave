/** What the writer last chose for the outline: the drawer tab, and whether it is pinned beside the text (spec 111). */
import { useState } from "react";

export type DrawerTab = "files" | "outline";

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
  const [tab, setTabState] = useState<DrawerTab>(() =>
    readFlag(TAB_KEY) === "outline" ? "outline" : "files",
  );
  const setTab = (next: DrawerTab) => {
    writeFlag(TAB_KEY, next);
    setTabState(next);
  };
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
