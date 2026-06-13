import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { useAuth } from "@/auth/auth-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { changeEmail } from "./api";
import { errMessage } from "./errMessage";

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
    <Card>
      <CardHeader>
        <CardTitle>{t("email.title")}</CardTitle>
        <CardDescription>
          {t("email.current")} <span className="font-medium">{user?.email}</span>
          {user?.pending_email && (
            <span className="ml-1 text-amber-600">
              {t("email.pending", { email: user.pending_email })}
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {sentTo ? (
          <p role="status" className="text-sm text-muted-foreground">
            {t("email.sentPrefix")}
            <span className="font-medium">{sentTo}</span>
            {t("email.sentSuffix")}
          </p>
        ) : (
          <form onSubmit={submit} className="space-y-4">
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
            <Button type="submit" disabled={busy || !newEmail.trim() || !password}>
              {busy ? t("email.sending") : t("email.submit")}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
