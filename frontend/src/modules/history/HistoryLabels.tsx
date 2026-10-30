/** Inline label badges with add/delete for editors/owners (spec 38). */
import { Tag, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

import type { LabelBrief } from "./types";

export function HistoryLabels({
  version,
  labels,
  canWrite,
  onAdd,
  onDelete,
}: {
  version: number;
  labels: LabelBrief[];
  canWrite: boolean;
  onAdd: (version: number, name: string) => void;
  onDelete: (labelId: string) => void;
}) {
  const { t } = useTranslation("history");
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");

  return (
    <div className="flex flex-wrap items-center gap-1">
      {labels.map((label) => (
        <Badge key={label.id} variant="secondary" className="gap-1">
          {label.name}
          {canWrite && (
            <button
              type="button"
              aria-label={t("labels.remove", { name: label.name })}
              className="rounded-sm hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(label.id);
              }}
            >
              <X className="size-3" />
            </button>
          )}
        </Badge>
      ))}
      {canWrite && (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              className="size-5"
              aria-label={t("labels.addToVersion", { version })}
              onClick={(e) => e.stopPropagation()}
            >
              <Tag className="size-3" />
            </Button>
          </PopoverTrigger>
          <PopoverContent
            className="w-56"
            onClick={(e) => e.stopPropagation()}
            onPointerDownCapture={(e) => e.stopPropagation()}
          >
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (name.trim()) {
                  onAdd(version, name.trim());
                  setName("");
                  setOpen(false);
                }
              }}
            >
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("labels.namePlaceholder")}
                aria-label={t("labels.nameAriaLabel")}
              />
              <Button type="submit" size="sm" disabled={!name.trim()}>
                {t("labels.add")}
              </Button>
            </form>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}
