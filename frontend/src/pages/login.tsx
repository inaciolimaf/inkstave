import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/auth-context";
import { InkstaveLogo } from "@/components/inkstave-logo";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
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
      navigate(state.from?.pathname ?? "/", { replace: true });
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
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-muted/30 p-4">
      <InkstaveLogo className="text-2xl" />
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">{t("login.title")}</CardTitle>
          <CardDescription>{t("login.description")}</CardDescription>
        </CardHeader>
        <CardContent>
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
          <div className="mt-4 flex flex-col items-center gap-1 text-sm">
            <Link
              to="/forgot-password"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              {t("login.forgotPassword")}
            </Link>
            <Link
              to="/magic-link"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              {t("login.magicLink")}
            </Link>
            <Link
              to="/verify-email/resend"
              className="text-muted-foreground underline-offset-4 hover:underline"
            >
              {t("login.resend")}
            </Link>
          </div>
          <p className="mt-4 text-center text-sm text-muted-foreground">
            {t("login.noAccount")}{" "}
            <Link
              to="/register"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              {t("login.createOne")}
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
