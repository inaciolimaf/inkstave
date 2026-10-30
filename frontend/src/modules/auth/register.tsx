import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { AuthFoot, AuthLink, AuthShell } from "./AuthShell";
import { useAuth } from "./auth-context";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api-client";
import { type RegisterValues, makeRegisterSchema } from "@/lib/validation";

const FIELD_NAMES = new Set(["email", "password", "display_name"]);

export function RegisterPage() {
  const { t } = useTranslation(["auth", "common"]);
  const { register } = useAuth();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);
  const schema = useMemo(() => makeRegisterSchema((k) => t(k)), [t]);

  const form = useForm<RegisterValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", display_name: "", password: "", confirm_password: "" },
  });

  const onSubmit = async (values: RegisterValues) => {
    setFormError(null);
    try {
      await register({
        email: values.email,
        password: values.password,
        display_name: values.display_name,
      });
      navigate("/login", { replace: true, state: { justRegistered: true } });
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 409) {
          setFormError(t("register.emailExists"));
        } else if (error.status === 422 && error.fieldErrors) {
          for (const [field, message] of Object.entries(error.fieldErrors)) {
            if (FIELD_NAMES.has(field)) {
              form.setError(field as keyof RegisterValues, { message });
            } else {
              setFormError(message);
            }
          }
        } else {
          setFormError(error.detail);
        }
      } else {
        setFormError(t("common:state.error"));
      }
    }
  };

  const pending = form.formState.isSubmitting;

  return (
    <AuthShell title={t("register.title")} description={t("register.description")}>
      {formError && (
        <Alert variant="destructive" className="mb-4" aria-live="assertive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <FormField
            control={form.control}
            name="display_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t("fields.displayName")}</FormLabel>
                <FormControl>
                  <Input autoComplete="name" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
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
                  <Input type="password" autoComplete="new-password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="confirm_password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t("fields.confirmPassword")}</FormLabel>
                <FormControl>
                  <Input type="password" autoComplete="new-password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" className="w-full" disabled={pending}>
            {pending && <Loader2 className="animate-spin" />}
            {t("register.submit")}
          </Button>
        </form>
      </Form>
      <AuthFoot>
        {t("register.haveAccount")} <AuthLink to="/login">{t("common:action.signIn")}</AuthLink>
      </AuthFoot>
    </AuthShell>
  );
}
