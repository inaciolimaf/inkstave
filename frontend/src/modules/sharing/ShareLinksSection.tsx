/** "Share with a link" section of the Share dialog: a view link and an edit link (spec 116). */
import { useTranslation } from "react-i18next";

import { QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";

import type { Confirm } from "./ConfirmDialog";
import type { LinkRole, ShareLink } from "./types";
import { useShareLinks } from "./useShareLinks";

const ROLES: LinkRole[] = ["editor", "viewer"];

type ShareLinkState = ReturnType<typeof useShareLinks>;

interface LinkRowProps {
  role: LinkRole;
  link: ShareLink | undefined;
  url: string | undefined;
  busy: boolean;
  onToggle: (role: LinkRole, on: boolean, link: ShareLink | undefined) => void;
  onCopy: (url: string) => void;
  onRotate: (role: LinkRole) => void;
}

function LinkRow({ role, link, url, busy, onToggle, onCopy, onRotate }: LinkRowProps) {
  const { t } = useTranslation("sharing");
  const on = link !== undefined;
  const id = `share-link-${role}`;
  return (
    <li className="flex flex-wrap items-center gap-2 text-body">
      <Switch
        id={id}
        checked={on}
        disabled={busy}
        onCheckedChange={(checked) => onToggle(role, checked, link)}
      />
      <Label htmlFor={id} className="mr-auto min-w-0 font-normal">
        {t(`links.${role}Label`)}
      </Label>
      {on && <span className="text-small text-muted-foreground">{t("links.on")}</span>}
      {on && url && (
        <Button size="sm" variant="outline" onClick={() => onCopy(url)}>
          {t("links.copy")}
        </Button>
      )}
      {on && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onRotate(role)}
          aria-label={t("links.rotateLabel", { role: t(`role.${role}`) })}
        >
          {t("links.rotate")}
        </Button>
      )}
      {on && !url && <p className="w-full text-small text-muted-foreground">{t("links.shownOnce")}</p>}
    </li>
  );
}

function ShareLinkRows({
  state,
  onConfirm,
}: {
  state: ShareLinkState;
  onConfirm: (confirm: Confirm) => void;
}) {
  const { t } = useTranslation("sharing");
  const { links, urls, create, revoke, copy } = state;

  const toggle = (role: LinkRole, checked: boolean, link: ShareLink | undefined) => {
    if (checked) create.mutate(role);
    else if (link) revoke.mutate(link);
  };

  const rotate = (role: LinkRole) =>
    onConfirm({
      title: t("links.rotateConfirm.title", { role: t(`role.${role}`) }),
      description: t("links.rotateConfirm.description"),
      action: t("links.rotateConfirm.action"),
      run: () => create.mutate(role),
    });

  return (
    <ul className="space-y-2">
      {ROLES.map((role) => (
        <LinkRow
          key={role}
          role={role}
          link={links.find((l) => l.role === role)}
          url={urls[role]}
          busy={create.isPending || revoke.isPending}
          onToggle={toggle}
          onCopy={(url) => void copy(url)}
          onRotate={rotate}
        />
      ))}
    </ul>
  );
}

export function ShareLinksSection({
  projectId,
  enabled,
  onConfirm,
}: {
  projectId: string;
  enabled: boolean;
  onConfirm: (confirm: Confirm) => void;
}) {
  const { t } = useTranslation("sharing");
  const state = useShareLinks(projectId, enabled);
  return (
    <section aria-label={t("links.title")} className="space-y-3">
      <div>
        <h3 className="text-body font-medium">{t("links.title")}</h3>
        <p className="text-small text-muted-foreground">{t("links.description")}</p>
      </div>
      <QueryView
        query={{
          data: state.linksQuery.data,
          isLoading: state.linksQuery.isLoading,
          isError: state.linksQuery.isError,
          refetch: () => void state.linksQuery.refetch(),
        }}
        loading={<Skeleton className="h-9 w-full" />}
        errorMessage={t("links.loadError")}
      >
        {() => <ShareLinkRows state={state} onConfirm={onConfirm} />}
      </QueryView>
    </section>
  );
}
