import { ForgotPasswordPage, PublicOnly } from "@/modules/auth";

export function ForgotPasswordRoute() {
  return (
    <PublicOnly>
      <ForgotPasswordPage />
    </PublicOnly>
  );
}
