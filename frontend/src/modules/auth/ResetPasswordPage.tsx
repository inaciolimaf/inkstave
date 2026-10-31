import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { ApiError } from "@/lib/api-client";
import { type ResetPasswordValues, makeResetPasswordSchema } from "@/lib/validation";

import { AuthField } from "./AuthField";
import { AuthShell } from "./AuthShell";
import { resetPassword } from "./api";

type State = { kind: "form" } | { kind: "success" } | { kind: "expired" } | { kind: "invalid" };

/** The reset form, its submission, and which of the page's states the link is in. */
function useResetPassword() {
  const { t } = useTranslation(["auth", "common"]);
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();
  const [state, setState] = useState<State>(() => (token ? { kind: "form" } : { kind: "invalid" }));

  const schema = useMemo(() => makeResetPasswordSchema((k) => t(k)), [t]);
  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirm_password: "" },
  });

  // Tokens were all revoked by the reset, so we cannot auto-login — send the user
  // to the sign-in page a moment after success.
  useEffect(() => {
    if (state.kind !== "success") return;
    const id = setTimeout(() => navigate("/login", { replace: true }), 1500);
    return () => clearTimeout(id);
  }, [state.kind, navigate]);

  const onSubmit = async (values: ResetPasswordValues) => {
    if (!token) {
      setState({ kind: "invalid" });
      return;
    }
    try {
      await resetPassword(token, values.password);
      setState({ kind: "success" });
    } catch (error) {
      if (error instanceof ApiError && error.status === 410) {
        setState({ kind: "expired" });
      } else if (error instanceof ApiError && error.status === 400 && error.fieldErrors) {
        // A server-side strength rejection maps onto the password field.
        const msg = error.fieldErrors.new_password ?? error.detail;
        form.setError("password", { message: msg });
      } else if (error instanceof ApiError && error.status === 400) {
        // Used/unknown token — distinct from an expired one.
        setState({ kind: "invalid" });
      } else {
        form.setError("password", { message: t("common:state.error") });
      }
    }
  };

  return { state, form, onSubmit };
}

function ResetSucceeded() {
  const { t } = useTranslation(["auth", "common"]);
  return (
    <AuthShell title={t("resetPassword.title")}>
      <Alert role="alert">
        <AlertDescription>{t("resetPassword.success")}</AlertDescription>
      </Alert>
      <Button asChild className="mt-4 w-full">
        <Link to="/login">{t("resetPassword.goToLogin")}</Link>
      </Button>
    </AuthShell>
  );
}

function ResetLinkDead({ kind }: { kind: "expired" | "invalid" }) {
  const { t } = useTranslation(["auth", "common"]);
  return (
    <AuthShell title={t("resetPassword.title")}>
      <Alert variant="destructive" role="alert">
        <AlertDescription>
          {kind === "expired" ? t("resetPassword.expired") : t("resetPassword.invalid")}
        </AlertDescription>
      </Alert>
      <Button asChild className="mt-4 w-full">
        <Link to="/forgot-password">{t("resetPassword.requestNew")}</Link>
      </Button>
    </AuthShell>
  );
}

export function ResetPasswordPage() {
  const { t } = useTranslation(["auth", "common"]);
  const { state, form, onSubmit } = useResetPassword();

  if (state.kind === "success") return <ResetSucceeded />;
  if (state.kind === "expired" || state.kind === "invalid") return <ResetLinkDead kind={state.kind} />;

  const pending = form.formState.isSubmitting;
  return (
    <AuthShell title={t("resetPassword.title")} description={t("resetPassword.description")}>
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <AuthField
            control={form.control}
            name="password"
            label={t("fields.newPassword")}
            type="password"
            autoComplete="new-password"
          />
          <AuthField
            control={form.control}
            name="confirm_password"
            label={t("fields.confirmNewPassword")}
            type="password"
            autoComplete="new-password"
          />
          <Button type="submit" className="w-full" disabled={pending}>
            {pending && <Loader2 className="animate-spin" />}
            {t("resetPassword.submit")}
          </Button>
        </form>
      </Form>
    </AuthShell>
  );
}
