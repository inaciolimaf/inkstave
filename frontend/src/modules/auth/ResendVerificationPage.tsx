import { useTranslation } from "react-i18next";

import { AuthFoot, AuthLink, AuthShell } from "./AuthShell";
import { EmailRequestForm } from "./EmailRequestForm";
import { resendVerification } from "./api";

export function ResendVerificationPage() {
  const { t } = useTranslation("auth");
  return (
    <AuthShell title={t("resendVerification.title")} description={t("resendVerification.description")}>
      <EmailRequestForm
        submitLabel={t("resendVerification.submit")}
        successMessage={t("resendVerification.success")}
        request={resendVerification}
      />
      <AuthFoot>
        <AuthLink to="/login">{t("resendVerification.backToLogin")}</AuthLink>
      </AuthFoot>
    </AuthShell>
  );
}
