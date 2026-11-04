import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { ProjectScope } from "./types";

const SCOPES: readonly ProjectScope[] = ["all", "owned", "shared"];

/** The All / Owned by me / Shared with me filter above the list (spec 109). */
export function ProjectScopeControl({
  value,
  onChange,
}: {
  value: ProjectScope;
  onChange: (scope: ProjectScope) => void;
}) {
  const { t } = useTranslation("projects");
  return (
    <div role="group" aria-label={t("scope.label")} className="flex flex-wrap gap-x-5 gap-y-2 py-3">
      {SCOPES.map((scope) => {
        const active = scope === value;
        return (
          <Button
            key={scope}
            type="button"
            variant="ghost"
            size="sm"
            aria-pressed={active}
            onClick={() => onChange(scope)}
            className={cn(
              "h-auto px-0 font-normal text-muted-foreground hover:bg-transparent hover:text-foreground",
              active && "font-medium text-foreground underline underline-offset-4",
            )}
          >
            {t(`scope.${scope}`)}
          </Button>
        );
      })}
    </div>
  );
}
