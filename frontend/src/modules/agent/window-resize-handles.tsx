/** What resizes the agent window: its top and left edges by pointer, its corner by pointer or keyboard. */
import { MoveDiagonal } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { useWindowSize } from "./use-window-size";

export function WindowResizeHandles({
  resize,
}: {
  resize: Pick<ReturnType<typeof useWindowSize>, "startDrag" | "onResizeKey">;
}) {
  const { t } = useTranslation("agent");
  return (
    <>
      <div
        aria-hidden="true"
        className="absolute inset-x-6 top-0 z-10 hidden h-1.5 cursor-ns-resize touch-none md:block"
        onPointerDown={(e) => resize.startDrag("top", e)}
      />
      <div
        aria-hidden="true"
        className="absolute inset-y-6 left-0 z-10 hidden w-1.5 cursor-ew-resize touch-none md:block"
        onPointerDown={(e) => resize.startDrag("left", e)}
      />
      <button
        type="button"
        aria-label={t("window.resize")}
        title={t("window.resizeHint")}
        className="absolute left-0 top-0 z-10 hidden size-6 cursor-nwse-resize touch-none place-items-center text-muted-foreground hover:text-foreground md:grid"
        onPointerDown={(e) => resize.startDrag("corner", e)}
        onKeyDown={resize.onResizeKey}
      >
        <MoveDiagonal aria-hidden="true" className="size-3.5" />
      </button>
    </>
  );
}
