import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/modules/auth";
import { InkstaveLogo } from "@/components/inkstave-logo";
import { Manuscript, ManuscriptHeader, Rule } from "@/components/manuscript";
import { Button } from "@/components/ui/button";
import { NotificationsBell } from "@/modules/notifications";

import { DangerZone } from "./DangerZone";
import { DictionarySection } from "./DictionarySection";
import { EditorPreferencesSection } from "./EditorPreferencesSection";
import { EmailSection } from "./EmailSection";
import { PasswordSection } from "./PasswordSection";
import { ProfileSection } from "./ProfileSection";

function SettingsBar() {
  const { t } = useTranslation(["settings", "common"]);
  const { logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex items-center justify-between px-4 py-3 sm:px-6">
      <InkstaveLogo />
      <div className="flex items-center gap-1">
        <NotificationsBell />
        <Button variant="ghost" size="sm" onClick={() => navigate("/projects")}>
          {t("page.backToProjects")}
        </Button>
        <Button variant="ghost" size="sm" onClick={onLogout}>
          {t("common:action.signOut")}
        </Button>
      </div>
    </div>
  );
}

export function SettingsPage() {
  const { t } = useTranslation("settings");
  return (
    <Manuscript bar={<SettingsBar />}>
      <ManuscriptHeader title={t("page.title")} />
      <Rule />
      <div className="mt-8 space-y-10">
        <ProfileSection />
        <EditorPreferencesSection />
        <DictionarySection />
        <EmailSection />
        <PasswordSection />
        <DangerZone />
      </div>
    </Manuscript>
  );
}
