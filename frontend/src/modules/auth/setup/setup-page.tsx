import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router-dom";
import { z } from "zod";

import { TitlePage } from "@/components/manuscript";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthShell } from "../AuthShell";
import { createFirstAdmin } from "./api";
import { useSetupStatus } from "./useSetupStatus";
import { ApiError } from "@/lib/api-client";
import { makePasswordSchema } from "@/lib/validation";

const makeSetupSchema = (t: (key: string) => string) =>
  z.object({
    display_name: z.string().min(1, t("validation.displayNameRequired")),
    email: z.string().min(1, t("validation.emailRequired")).email(t("validation.emailInvalid")),
    password: makePasswordSchema(t),
  });

type SetupValues = z.infer<ReturnType<typeof makeSetupSchema>>;

/** First-run admin creation (spec 63). Public route; only useful when no admin exists. */
export function SetupPage() {
  const { t } = useTranslation(["auth", "common"]);
  const status = useSetupStatus();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);
  const setupSchema = useMemo(() => makeSetupSchema((k) => t(k)), [t]);

  const form = useForm<SetupValues>({
    resolver: zodResolver(setupSchema),
    defaultValues: { display_name: "", email: "", password: "" },
  });

  if (status.isLoading) {
    return (
      <TitlePage>
        <div className="space-y-3" aria-busy="true">
          <Skeleton className="h-8" />
          <Skeleton className="h-24" />
        </div>
      </TitlePage>
    );
  }

  if (status.isError) {
    return (
      <AuthShell title={t("setup.title")}>
        <Alert variant="destructive" role="alert">
          <AlertDescription>{t("setup.statusError")}</AlertDescription>
        </Alert>
      </AuthShell>
    );
  }

  // Setup already done — nothing to do here.
  if (status.data && !status.data.needsSetup) {
    return <Navigate to="/login" replace />;
  }

  const onSubmit = async (values: SetupValues) => {
    setFormError(null);
    try {
      await createFirstAdmin({
        email: values.email,
        password: values.password,
        displayName: values.display_name,
      });
      navigate("/login", { replace: true, state: { justSetUp: true } });
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 409) {
          setFormError(t("setup.alreadyComplete"));
        } else if (error.status === 422 && error.fieldErrors) {
          for (const [field, message] of Object.entries(error.fieldErrors)) {
            if (field === "email" || field === "password" || field === "display_name") {
              form.setError(field as keyof SetupValues, { message });
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
    <AuthShell title={t("setup.title")} description={t("setup.description")}>
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
                    placeholder={t("fields.adminEmailPlaceholder")}
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
          <Button type="submit" className="w-full" disabled={pending}>
            {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t("setup.submit")}
          </Button>
        </form>
      </Form>
    </AuthShell>
  );
}
