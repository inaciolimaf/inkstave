import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";

import { DangerZone } from "./DangerZone";
import { EditorPreferencesSection } from "./EditorPreferencesSection";
import { EmailSection } from "./EmailSection";
import { PasswordSection } from "./PasswordSection";
import { ProfileSection } from "./ProfileSection";

export function SettingsPage() {
  const { t } = useTranslation("settings");
  const navigate = useNavigate();
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t("page.title")}</h1>
        <Button variant="ghost" onClick={() => navigate("/projects")}>
          {t("page.backToProjects")}
        </Button>
      </div>
      <ProfileSection />
      <EditorPreferencesSection />
      <EmailSection />
      <PasswordSection />
      <DangerZone />
    </div>
  );
}
