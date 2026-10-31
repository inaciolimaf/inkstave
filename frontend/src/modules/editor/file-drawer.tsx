import { type KeyboardEvent, type ReactNode, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

/**
 * The file list, on top of the text (spec 107). The shade behind it says the text is out of reach until
 * the drawer closes; the host makes that true with `inert`. It stays mounted so the tree keeps its state.
 */
export function FileDrawer({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation("editor");
  const ref = useRef<HTMLElement>(null);
  const opener = useRef<HTMLElement | null>(null);

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
        {children}
      </aside>
    </>
  );
}
