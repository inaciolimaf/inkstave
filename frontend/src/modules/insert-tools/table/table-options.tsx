import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { labelFor } from "./to-latex";
import type { UpdateDraft } from "./table-grid";
import type { TableDraft, TableStyle } from "./table-model";

const STYLES: TableStyle[] = ["booktabs", "grid"];

/** A caption change moves the label along, until the person has typed a label of their own. */
function captionChange(draft: TableDraft, caption: string): TableDraft {
  const label = draft.label === labelFor(draft.caption) ? labelFor(caption) : draft.label;
  return { ...draft, caption, label };
}

function Check({
  id,
  checked,
  onChange,
  children,
}: {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: string;
}) {
  return (
    <div className="flex items-center gap-2 text-small">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="size-4 accent-foreground"
      />
      <Label htmlFor={id}>{children}</Label>
    </div>
  );
}

/** The table's settings: rule style, header, caption, label, float placement and whether cells are LaTeX. */
export function TableOptions({ draft, update }: { draft: TableDraft; update: UpdateDraft }) {
  const { t } = useTranslation("insert");
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-1">
        <Label htmlFor="table-style">{t("table.style")}</Label>
        <select
          id="table-style"
          value={draft.style}
          onChange={(event) => update((d) => ({ ...d, style: event.target.value as TableStyle }))}
          className="h-9 w-full rounded border bg-background px-2 text-small"
        >
          {STYLES.map((style) => (
            <option key={style} value={style}>
              {t(`table.styles.${style}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <Label htmlFor="table-placement">{t("table.placement")}</Label>
        <Input
          id="table-placement"
          value={draft.placement}
          onChange={(event) => update((d) => ({ ...d, placement: event.target.value }))}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="table-caption">{t("table.caption")}</Label>
        <Input
          id="table-caption"
          value={draft.caption}
          onChange={(event) => update((d) => captionChange(d, event.target.value))}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="table-label">{t("table.label")}</Label>
        <Input
          id="table-label"
          value={draft.label}
          onChange={(event) => update((d) => ({ ...d, label: event.target.value }))}
        />
      </div>
      <Check id="table-header" checked={draft.header} onChange={(v) => update((d) => ({ ...d, header: v }))}>
        {t("table.header")}
      </Check>
      <Check
        id="table-latex"
        checked={draft.cellsAreLatex}
        onChange={(v) => update((d) => ({ ...d, cellsAreLatex: v }))}
      >
        {t("table.cellsAreLatex")}
      </Check>
    </div>
  );
}
