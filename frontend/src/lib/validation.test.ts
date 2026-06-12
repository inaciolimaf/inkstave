import { describe, expect, it } from "vitest";

import { loginSchema, passwordSchema, registerSchema } from "./validation";

describe("loginSchema", () => {
  it("accepts a valid email and password", () => {
    expect(loginSchema.safeParse({ email: "a@b.com", password: "x" }).success).toBe(true);
  });
  it("rejects an invalid email", () => {
    expect(loginSchema.safeParse({ email: "nope", password: "x" }).success).toBe(false);
  });
});

describe("passwordSchema", () => {
  it.each([
    ["short1", false],
    ["abcdefgh", false],
    ["12345678", false],
    ["secret123", true],
  ])("validates %s -> %s", (value, ok) => {
    expect(passwordSchema.safeParse(value).success).toBe(ok);
  });
});

describe("registerSchema", () => {
  const base = {
    email: "a@b.com",
    display_name: "Alice",
    password: "secret123",
    confirm_password: "secret123",
  };

  it("accepts a valid payload", () => {
    expect(registerSchema.safeParse(base).success).toBe(true);
  });

  it("rejects mismatched passwords with a confirm_password error", () => {
    const result = registerSchema.safeParse({ ...base, confirm_password: "different1" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.path.includes("confirm_password"))).toBe(true);
    }
  });

  it("rejects an empty display name", () => {
    expect(registerSchema.safeParse({ ...base, display_name: "   " }).success).toBe(false);
  });
});
