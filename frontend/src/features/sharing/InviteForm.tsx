/** Invite-by-email form with inline validation and server-error display (spec 33). */
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { EMAIL_RE } from "./useSharing";
import type { InviteRole } from "./types";

export function InviteForm({
  email,
  setEmail,
  inviteRole,
  setInviteRole,
  inviteError,
  setInviteError,
  isPending,
  onSubmit,
}: {
  email: string;
  setEmail: (value: string) => void;
  inviteRole: InviteRole;
  setInviteRole: (role: InviteRole) => void;
  inviteError: string | null;
  setInviteError: (value: string | null) => void;
  isPending: boolean;
  onSubmit: () => void;
}) {
  const { t } = useTranslation("sharing");
  const emailValid = EMAIL_RE.test(email.trim());

  return (
    <>
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (emailValid) {
            setInviteError(null);
            onSubmit();
          }
        }}
      >
        <div className="flex-1">
          <label htmlFor="invite-email" className="text-sm font-medium">
            {t("invite.label")}
          </label>
          <Input
            id="invite-email"
            type="email"
            placeholder={t("invite.placeholder")}
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              if (inviteError) setInviteError(null);
            }}
            aria-invalid={(email.length > 0 && !emailValid) || inviteError !== null}
            aria-describedby={inviteError ? "invite-error" : undefined}
          />
        </div>
        <Select value={inviteRole} onValueChange={(v) => setInviteRole(v as InviteRole)}>
          <SelectTrigger className="w-28 capitalize" aria-label={t("invite.roleLabel")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="editor" className="capitalize">
              {t("role.editor")}
            </SelectItem>
            <SelectItem value="viewer" className="capitalize">
              {t("role.viewer")}
            </SelectItem>
          </SelectContent>
        </Select>
        <Button type="submit" disabled={!emailValid || isPending}>
          {t("invite.submit")}
        </Button>
      </form>
      {email.length > 0 && !emailValid && (
        <p className="text-sm text-destructive">{t("invite.invalidEmail")}</p>
      )}
      {inviteError && (
        <p id="invite-error" className="text-sm text-destructive" role="alert">
          {inviteError}
        </p>
      )}
    </>
  );
}
