import { useEffect, useRef } from "react";

/** Key → handler. `mod+s` means Ctrl or Cmd plus S; a bare key is ignored while typing. */
export type ShortcutMap = Record<string, (event: KeyboardEvent) => void>;

const MOD_PREFIX = "mod+";

function isTextField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

function handlerFor(shortcuts: ShortcutMap, event: KeyboardEvent) {
  const key = event.key.toLowerCase();
  if (event.metaKey || event.ctrlKey) return shortcuts[`${MOD_PREFIX}${key}`];
  return isTextField(event.target) ? undefined : shortcuts[key];
}

/**
 * The only place that listens to the keyboard. A matched shortcut suppresses the browser's own
 * action. The map goes through a ref, so a new object on each render does not rebind the listener.
 */
export function useShortcuts(shortcuts: ShortcutMap, active = true): void {
  const latest = useRef(shortcuts);
  latest.current = shortcuts;

  useEffect(() => {
    if (!active) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const handler = handlerFor(latest.current, event);
      if (!handler) return;
      event.preventDefault();
      handler(event);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [active]);
}
