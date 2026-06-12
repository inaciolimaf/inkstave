import { z } from "zod";

/** Password rules mirroring the backend (spec 06): 8-72 chars, letter + digit. */
export const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters.")
  .max(72, "Password must be at most 72 characters.")
  .refine((value) => /[A-Za-z]/.test(value), "Password must contain at least one letter.")
  .refine((value) => /\d/.test(value), "Password must contain at least one digit.");

export const loginSchema = z.object({
  email: z.string().min(1, "Email is required.").email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

export const registerSchema = z
  .object({
    email: z.string().min(1, "Email is required.").email("Enter a valid email address."),
    display_name: z
      .string()
      .trim()
      .min(1, "Display name is required.")
      .max(100, "Display name must be at most 100 characters."),
    password: passwordSchema,
    confirm_password: z.string().min(1, "Please confirm your password."),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Passwords do not match.",
    path: ["confirm_password"],
  });

export type LoginValues = z.infer<typeof loginSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
