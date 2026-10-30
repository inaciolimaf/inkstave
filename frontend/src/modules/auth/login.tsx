import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { AuthFoot, AuthLink, AuthShell } from "./AuthShell";
import { useAuth } from "./auth-context";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api-client";
import { type LoginValues, makeLoginSchema } from "@/lib/validation";

interface LocationState {
  from?: { pathname?: string };
  justRegistered?: boolean;
}

export function LoginPage() {
  const { t } = useTranslation(["auth", "common"]);
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as LocationState;
  const [formError, setFormError] = useState<string | null>(null);
  const schema = useMemo(() => makeLoginSchema((k) => t(k)), [t]);

  const form = useForm<LoginValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = async (values: LoginValues) => {
    setFormError(null);
    try {
      await login(values.email, values.password);
      // After login go to where the user was headed, else the app dashboard.
      // NOT "/" — that is the public marketing landing, not the signed-in home.
      navigate(state.from?.pathname ?? "/projects", { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 401) setFormError(t("login.invalidCredentials"));
        else if (error.status === 429) setFormError(t("login.tooManyAttempts"));
        else setFormError(error.detail);
      } else {
        setFormError(t("common:state.error"));
      }
    }
  };

  const pending = form.formState.isSubmitting;

  return (
    <AuthShell title={t("login.title")} description={t("login.description")}>
      {state.justRegistered && (
        <Alert className="mb-4">
          <AlertDescription>{t("login.justRegistered")}</AlertDescription>
        </Alert>
      )}
      {formError && (
        <Alert variant="destructive" className="mb-4" aria-live="assertive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t("fields.email")}</FormLabel>
                <FormControl>
                  <Input
                    type="email"
                    autoComplete="email"
                    placeholder={t("fields.emailPlaceholder")}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t("fields.password")}</FormLabel>
                <FormControl>
                  <Input type="password" autoComplete="current-password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" className="w-full" disabled={pending}>
            {pending && <Loader2 className="animate-spin" />}
            {t("login.submit")}
          </Button>
        </form>
      </Form>
      <div className="mt-6 flex flex-col items-start gap-1 text-body">
        <AuthLink to="/forgot-password">{t("login.forgotPassword")}</AuthLink>
        <AuthLink to="/magic-link">{t("login.magicLink")}</AuthLink>
        <AuthLink to="/verify-email/resend">{t("login.resend")}</AuthLink>
      </div>
      <AuthFoot>
        {t("login.noAccount")} <AuthLink to="/register">{t("login.createOne")}</AuthLink>
      </AuthFoot>
    </AuthShell>
  );
}
