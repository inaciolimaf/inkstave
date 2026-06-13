import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { AuthShell } from "./AuthShell";
import { EmailRequestForm } from "./EmailRequestForm";
import { resendVerification } from "./api";

export function ResendVerificationPage() {
  const { t } = useTranslation("auth");
  return (
    <AuthShell
      title={t("resendVerification.title")}
      description={t("resendVerification.description")}
    >
      <EmailRequestForm
        submitLabel={t("resendVerification.submit")}
        successMessage={t("resendVerification.success")}
        request={resendVerification}
      />
      <p className="mt-4 text-center text-sm text-muted-foreground">
        <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
          {t("resendVerification.backToLogin")}
        </Link>
      </p>
    </AuthShell>
  );
}
