/**
 * Thin API wrapper for the email link-based auth flows (spec 104).
 *
 * Every call is pre-login (`auth: false` — no Bearer token, no refresh-on-401),
 * mirroring `features/settings/api.ts`. The callback endpoints surface their
 * 400 (invalid/used) vs 410 (expired) status via the thrown `ApiError`.
 */
import { apiClient } from "@/lib/api-client";
import type { TokenPair, UserPublic } from "@/types";

interface MessageResponse {
  detail: string;
}

export function resendVerification(email: string): Promise<MessageResponse> {
  return apiClient.post<MessageResponse>(
    "/api/v1/auth/verify-email/resend",
    { email },
    { auth: false },
  );
}

export function confirmVerification(token: string): Promise<UserPublic> {
  return apiClient.post<UserPublic>(
    "/api/v1/auth/verify-email/confirm",
    { token },
    { auth: false },
  );
}

export function requestMagicLink(email: string): Promise<MessageResponse> {
  return apiClient.post<MessageResponse>("/api/v1/auth/magic-link", { email }, { auth: false });
}

export function completeMagicLink(token: string): Promise<TokenPair> {
  return apiClient.post<TokenPair>("/api/v1/auth/magic-link/callback", { token }, { auth: false });
}

export function requestPasswordReset(email: string): Promise<MessageResponse> {
  return apiClient.post<MessageResponse>(
    "/api/v1/auth/forgot-password",
    { email },
    { auth: false },
  );
}

export function resetPassword(token: string, new_password: string): Promise<MessageResponse> {
  return apiClient.post<MessageResponse>(
    "/api/v1/auth/reset-password",
    { token, new_password },
    { auth: false },
  );
}
