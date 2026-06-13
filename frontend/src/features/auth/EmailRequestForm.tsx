import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
import { type EmailRequestValues, makeEmailRequestSchema } from "@/lib/validation";

/**
 * Email-only request form shared by the non-enumerating flows (forgot-password,
 * magic-link request, resend verification). Always shows the same success copy
 * regardless of whether the address exists; a network/validation failure shows
 * an error, but a 429 surfaces as a too-many-requests message.
 */
export function EmailRequestForm({
  submitLabel,
  successMessage,
  request,
}: {
  submitLabel: string;
  successMessage: string;
  request: (email: string) => Promise<unknown>;
}) {
  const { t } = useTranslation(["auth", "common"]);
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const schema = useMemo(() => makeEmailRequestSchema((k) => t(k)), [t]);
  const form = useForm<EmailRequestValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });

  const onSubmit = async (values: EmailRequestValues) => {
    setFormError(null);
    try {
      await request(values.email);
      setSubmitted(true);
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setFormError(t("login.tooManyAttempts"));
      } else {
        setFormError(t("common:state.error"));
      }
    }
  };

  if (submitted) {
    return (
      <Alert role="alert">
        <AlertDescription>{successMessage}</AlertDescription>
      </Alert>
    );
  }

  const pending = form.formState.isSubmitting;
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {formError && (
          <Alert variant="destructive" role="alert" aria-live="assertive">
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        )}
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
        <Button type="submit" className="w-full" disabled={pending}>
          {pending && <Loader2 className="animate-spin" />}
          {submitLabel}
        </Button>
      </form>
    </Form>
  );
}
