import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate } from "react-router-dom";
import { z } from "zod";

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
import { passwordSchema } from "@/lib/validation";

const setupSchema = z.object({
  display_name: z.string().min(1, "Display name is required."),
  email: z.string().min(1, "Email is required.").email("Enter a valid email address."),
  password: passwordSchema,
});

type SetupValues = z.infer<typeof setupSchema>;

/** First-run admin creation (spec 63). Public route; only useful when no admin exists. */
export function SetupPage() {
  const status = useSetupStatus();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);

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
          <AlertDescription>
            Couldn’t reach the server to check setup status. Please try again.
          </AlertDescription>
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
          setFormError("Setup is already complete. Redirecting to sign in…");
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
        setFormError("Something went wrong. Please try again.");
      }
    }
  };

  const pending = form.formState.isSubmitting;

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">Set up Inkstave</CardTitle>
          <CardDescription>Create the first administrator account.</CardDescription>
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
                    <FormLabel>Display name</FormLabel>
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
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input
                        type="email"
                        autoComplete="email"
                        placeholder="admin@example.com"
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
                    <FormLabel>Password</FormLabel>
                    <FormControl>
                      <Input type="password" autoComplete="new-password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" className="w-full" disabled={pending}>
                {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Create admin
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
