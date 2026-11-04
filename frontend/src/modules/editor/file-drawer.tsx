import { type KeyboardEvent, type ReactNode, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import { type DrawerTab, useDrawerTab } from "./outline-prefs";

function TabButton({
  tab,
  current,
  onSelect,
  children,
}: {
  tab: DrawerTab;
  current: DrawerTab;
  onSelect: (tab: DrawerTab) => void;
  children: ReactNode;
}) {
  const active = tab === current;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => onSelect(tab)}
      className={cn(
        "flex-1 border-b-2 px-2 py-1.5 font-medium",
        active
          ? "border-foreground text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/**
 * The file list, on top of the text (spec 107), with the outline beside it as a second tab (spec 111). The shade
 * behind it says the text is out of reach until the drawer closes; the host makes that true with `inert`. It stays
 * mounted so the tree keeps its state.
 */
export function FileDrawer({
  open,
  onClose,
  children,
  outline,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  outline?: ReactNode;
}) {
  const { t } = useTranslation("editor");
  const ref = useRef<HTMLElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [tab, setTab] = useDrawerTab();

  useEffect(() => {
    if (open) {
      opener.current = document.activeElement as HTMLElement | null;
      ref.current?.focus();
    } else if (opener.current) {
      opener.current.focus();
      opener.current = null;
    }
  }, [open]);

  // A dialog opened from the tree portals out of the drawer but still bubbles here through React.
  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    const target = e.target as HTMLElement;
    if (e.key !== "Escape" || !e.currentTarget.contains(target) || target.tagName === "INPUT") return;
    onClose();
  };

  return (
    <>
      {open && (
        <button
          type="button"
          tabIndex={-1}
          aria-label={t("drawer.shade")}
          onClick={onClose}
          className="absolute inset-0 z-20 bg-backdrop/50"
        />
      )}
      <aside
        ref={ref}
        tabIndex={-1}
        hidden={!open}
        aria-label={t("toolbar.files")}
        onKeyDown={onKeyDown}
        className="absolute inset-y-0 left-0 z-20 w-60 max-w-[80%] border-r border-control-edge bg-background shadow-xl outline-none"
      >
        {outline ? (
          // No `flex` on the aside itself: it would override the `hidden` attribute that closes the drawer.
          <div className="flex h-full flex-col">
            <div
              role="tablist"
              aria-label={t("drawer.tabs")}
              className="flex shrink-0 border-b border-control-edge text-small"
            >
              <TabButton tab="files" current={tab} onSelect={setTab}>
                {t("drawer.files")}
              </TabButton>
              <TabButton tab="outline" current={tab} onSelect={setTab}>
                {t("drawer.outline")}
              </TabButton>
            </div>
            <div role="tabpanel" hidden={tab !== "files"} className="min-h-0 flex-1 overflow-auto">
              {children}
            </div>
            <div role="tabpanel" hidden={tab !== "outline"} className="min-h-0 flex-1 overflow-auto">
              {outline}
            </div>
          </div>
        ) : (
          children
        )}
      </aside>
    </>
  );
}
