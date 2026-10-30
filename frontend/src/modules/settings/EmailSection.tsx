import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { useAuth } from "@/modules/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { changeEmail } from "./api";
import { errMessage } from "./errMessage";
import { SettingsSection } from "./SettingsSection";

export function EmailSection() {
  const { t } = useTranslation("settings");
  const { user, refreshUser } = useAuth();
  const [newEmail, setNewEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await changeEmail({ new_email: newEmail.trim(), current_password: password });
      setSentTo(newEmail.trim());
      setNewEmail("");
      setPassword("");
      await refreshUser();
      toast.success(t("email.success"));
    } catch (err) {
      toast.error(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SettingsSection
      title={t("email.title")}
      description={
        <>
          {t("email.current")} <span className="font-medium">{user?.email}</span>
          {user?.pending_email && (
            <span className="ml-1">{t("email.pending", { email: user.pending_email })}</span>
          )}
        </>
      }
    >
      {sentTo ? (
        <p role="status" className="text-body text-muted-foreground">
          {t("email.sentPrefix")}
          <span className="font-medium">{sentTo}</span>
          {t("email.sentSuffix")}
        </p>
      ) : (
        <form onSubmit={submit} className="max-w-md space-y-4">
          <div className="space-y-1">
            <Label htmlFor="new-email">{t("email.newEmail")}</Label>
            <Input
              id="new-email"
              type="email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="email-pw">{t("email.password")}</Label>
            <Input
              id="email-pw"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <Button type="submit" variant="outline" disabled={busy || !newEmail.trim() || !password}>
            {busy ? t("email.sending") : t("email.submit")}
          </Button>
        </form>
      )}
    </SettingsSection>
  );
}
