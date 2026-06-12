import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router-dom";
import { z } from "zod";

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
import { Skeleton } from "@/components/ui/skeleton";
import { createFirstAdmin } from "@/features/setup/api";
import { useSetupStatus } from "@/features/setup/useSetupStatus";
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
      <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
        <div className="w-full max-w-sm space-y-3" aria-busy="true">
          <Skeleton className="h-8" />
          <Skeleton className="h-24" />
        </div>
      </div>
    );
  }

  if (status.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
        <Alert variant="destructive" className="w-full max-w-sm" role="alert">
          <AlertDescription>{t("setup.statusError")}</AlertDescription>
        </Alert>
      </div>
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
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-muted/30 p-4">
      <InkstaveLogo className="text-2xl" />
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">{t("setup.title")}</CardTitle>
          <CardDescription>{t("setup.description")}</CardDescription>
        </CardHeader>
        <CardContent>
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
        </CardContent>
      </Card>
    </div>
  );
}
