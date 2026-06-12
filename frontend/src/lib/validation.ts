import { z } from "zod";

import i18n from "@/i18n/config";

/**
 * Form schemas. Messages are i18n keys in the `auth` namespace, resolved via a
 * `t` passed into the factory so they follow the active language. Build the
 * schema inside the component (useMemo over `t`). The pre-built `*Schema`
 * exports below use a default translator (English at import time) for non-React
 * consumers and tests, where only parse success/failure matters.
 */

type Translate = (key: string) => string;

/** Password rules mirroring the backend (spec 06): 8-72 chars, letter + digit. */
export const makePasswordSchema = (t: Translate) =>
  z
    .string()
    .min(8, t("validation.passwordMin"))
    .max(72, t("validation.passwordMax"))
    .refine((value) => /[A-Za-z]/.test(value), t("validation.passwordLetter"))
    .refine((value) => /\d/.test(value), t("validation.passwordDigit"));

export const makeLoginSchema = (t: Translate) =>
  z.object({
    email: z.string().min(1, t("validation.emailRequired")).email(t("validation.emailInvalid")),
    password: z.string().min(1, t("validation.passwordRequired")),
  });

export const makeRegisterSchema = (t: Translate) =>
  z
    .object({
      email: z.string().min(1, t("validation.emailRequired")).email(t("validation.emailInvalid")),
      display_name: z
        .string()
        .trim()
        .min(1, t("validation.displayNameRequired"))
        .max(100, t("validation.displayNameMax")),
      password: makePasswordSchema(t),
      confirm_password: z.string().min(1, t("validation.confirmPasswordRequired")),
    })
    .refine((data) => data.password === data.confirm_password, {
      message: t("validation.passwordsMismatch"),
      path: ["confirm_password"],
    });

const defaultT: Translate = (key) => i18n.t(key, { ns: "auth" });

export const passwordSchema = makePasswordSchema(defaultT);
export const loginSchema = makeLoginSchema(defaultT);
export const registerSchema = makeRegisterSchema(defaultT);

export type LoginValues = z.infer<typeof loginSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
