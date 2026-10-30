import { useTranslation } from "react-i18next";

import { AuthFoot, AuthLink, AuthShell } from "./AuthShell";
import { EmailRequestForm } from "./EmailRequestForm";
import { requestPasswordReset } from "./api";

export function ForgotPasswordPage() {
  const { t } = useTranslation("auth");
  return (
    <AuthShell title={t("forgotPassword.title")} description={t("forgotPassword.description")}>
      <EmailRequestForm
        submitLabel={t("forgotPassword.submit")}
        successMessage={t("forgotPassword.success")}
        request={requestPasswordReset}
      />
      <AuthFoot>
        <AuthLink to="/login">{t("forgotPassword.backToLogin")}</AuthLink>
      </AuthFoot>
    </AuthShell>
  );
}
