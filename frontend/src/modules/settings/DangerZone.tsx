import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useAuth } from "@/modules/auth";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { deleteAccount } from "./api";
import { errMessage } from "./errMessage";
import { SettingsSection } from "./SettingsSection";

export function DangerZone() {
  const { t } = useTranslation(["settings", "common"]);
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    try {
      await deleteAccount(password);
      toast.success(t("danger.success"));
      await logout();
      navigate("/login");
    } catch (err) {
      toast.error(errMessage(err));
      setBusy(false);
    }
  }

  return (
    <SettingsSection title={t("danger.title")} description={t("danger.description")}>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="outline" className="text-error-text hover:text-error-text">
            {t("danger.trigger")}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("danger.dialogTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("danger.dialogDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="del-pw">{t("danger.password")}</Label>
              <Input
                id="del-pw"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="del-confirm">{t("danger.typeDelete")}</Label>
              <Input
                id="del-confirm"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                autoComplete="off"
              />
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common:action.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void remove();
              }}
              disabled={busy || typed !== "DELETE" || !password}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {busy ? t("danger.deleting") : t("danger.submit")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SettingsSection>
  );
}
