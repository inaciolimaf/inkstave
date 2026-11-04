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

/** The drawer's tabs, in order, with the label key of each. */
const TAB_LABELS: { tab: DrawerTab; label: string }[] = [
  { tab: "files", label: "drawer.files" },
  { tab: "outline", label: "drawer.outline" },
  { tab: "search", label: "drawer.search" },
];

/** The tabbed body of the drawer: the file list, and beside it whichever of outline and search the host gives. */
function DrawerTabs({
  tab,
  onTab,
  panels,
}: {
  tab: DrawerTab;
  onTab: (tab: DrawerTab) => void;
  panels: Record<DrawerTab, ReactNode>;
}) {
  const { t } = useTranslation("editor");
  const shown = TAB_LABELS.filter(({ tab: name }) => panels[name] !== undefined);
  const current = shown.some(({ tab: name }) => name === tab) ? tab : "files";
  return (
    // No `flex` on the aside itself: it would override the `hidden` attribute that closes the drawer.
    <div className="flex h-full flex-col">
      <div
        role="tablist"
        aria-label={t("drawer.tabs")}
        className="flex shrink-0 border-b border-control-edge text-small"
      >
        {shown.map(({ tab: name, label }) => (
          <TabButton key={name} tab={name} current={current} onSelect={onTab}>
            {t(label)}
          </TabButton>
        ))}
      </div>
      {shown.map(({ tab: name }) => (
        <div key={name} role="tabpanel" hidden={current !== name} className="min-h-0 flex-1 overflow-auto">
          {panels[name]}
        </div>
      ))}
    </div>
  );
}

/**
 * The file list, on top of the text (spec 107), with the outline (spec 111) and the project search (spec 122) as
 * further tabs. The shade behind it says the text is out of reach until the drawer closes; the host makes that true
 * with `inert`. It stays mounted so the tree keeps its state. The host may hold the tab, to open the search from a
 * shortcut; otherwise the drawer holds it.
 */
export function FileDrawer({
  open,
  onClose,
  children,
  outline,
  search,
  tab: hostTab,
  onTabChange,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  outline?: ReactNode;
  search?: ReactNode;
  tab?: DrawerTab;
  onTabChange?: (tab: DrawerTab) => void;
}) {
  const { t } = useTranslation("editor");
  const ref = useRef<HTMLElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [ownTab, setOwnTab] = useDrawerTab();
  const tab = hostTab ?? ownTab;
  const setTab = onTabChange ?? setOwnTab;

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
        className={cn(
          "absolute inset-y-0 left-0 z-20 max-w-[80%] border-r border-control-edge bg-background shadow-xl outline-none",
          search && tab === "search" ? "w-80" : "w-60",
        )}
      >
        {outline || search ? (
          <DrawerTabs tab={tab} onTab={setTab} panels={{ files: children, outline, search }} />
        ) : (
          children
        )}
      </aside>
    </>
  );
}
