import type { EditorView } from "@codemirror/view";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

import { addPackage, hasBeginDocument, hasPackage, packageLine } from "./insert-text";

/**
 * One line under a tool whose result needs a package the main document does not load (spec 114 §5.2).
 * "Add it" writes the line before `\begin{document}` of the open text, when the open text has one.
 */
export function PackageHint({
  pkg,
  mainText,
  view,
}: {
  pkg: string | undefined;
  mainText: string;
  view: EditorView;
}) {
  const { t } = useTranslation("insert");
  const [added, setAdded] = useState<string[]>([]);
  if (!pkg || added.includes(pkg) || hasPackage(mainText, pkg)) return null;
  const line = packageLine(pkg);
  const onAdd = () => {
    if (addPackage(view, pkg)) setAdded((list) => [...list, pkg]);
  };
  return (
    <div role="status" className="flex flex-wrap items-center gap-2 text-small text-muted-foreground">
      <span>{t("packageHint.needs", { line })}</span>
      {hasBeginDocument(view) ? (
        <Button size="sm" variant="outline" onClick={onAdd}>
          {t("packageHint.add")}
        </Button>
      ) : (
        <span>{t("packageHint.noMainDocument", { line })}</span>
      )}
    </div>
  );
}
