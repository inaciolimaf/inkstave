import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { AuthShell } from "./AuthShell";
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
      <p className="mt-4 text-center text-sm text-muted-foreground">
        <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
          {t("forgotPassword.backToLogin")}
        </Link>
      </p>
    </AuthShell>
  );
}
