import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useAuth } from "@/modules/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { changePassword } from "./api";
import { errMessage } from "./errMessage";
import { SettingsSection } from "./SettingsSection";

export function PasswordSection() {
  const { t } = useTranslation("settings");
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const mismatch = confirm.length > 0 && next !== confirm;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (next !== confirm) return;
    setBusy(true);
    try {
      await changePassword({ current_password: current, new_password: next });
      toast.success(t("password.success"));
      await logout();
      navigate("/login");
    } catch (err) {
      toast.error(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SettingsSection title={t("password.title")} description={t("password.description")}>
      <form onSubmit={submit} className="max-w-md space-y-4">
        <div className="space-y-1">
          <Label htmlFor="cur-pw">{t("password.current")}</Label>
          <Input
            id="cur-pw"
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="new-pw">{t("password.new")}</Label>
          <Input
            id="new-pw"
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            minLength={8}
            required
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="confirm-pw">{t("password.confirm")}</Label>
          <Input
            id="confirm-pw"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            aria-invalid={mismatch}
            required
          />
          {mismatch && <p className="text-body text-error-text">{t("password.mismatch")}</p>}
        </div>
        <Button type="submit" variant="outline" disabled={busy || !current || !next || next !== confirm}>
          {busy ? t("password.changing") : t("password.submit")}
        </Button>
      </form>
    </SettingsSection>
  );
}
