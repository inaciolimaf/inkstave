/** Account-settings API calls (spec 59). Thin wrappers over the apiClient. */

import { apiClient } from "@/lib/api-client";
import type { EditorPreferences, UserPublic } from "@/types";

interface MessageResponse {
  detail: string;
}

export function updateProfile(patch: {
  display_name?: string;
  avatar_url?: string | null;
}): Promise<UserPublic> {
  return apiClient.patch<UserPublic>("/api/v1/users/me", patch);
}

export function putEditorPreferences(prefs: EditorPreferences): Promise<EditorPreferences> {
  return apiClient.put<EditorPreferences>("/api/v1/users/me/editor-preferences", prefs);
}

export function changePassword(body: {
  current_password: string;
  new_password: string;
}): Promise<MessageResponse> {
  return apiClient.post<MessageResponse>("/api/v1/users/me/change-password", body);
}

export function changeEmail(body: {
  new_email: string;
  current_password: string;
}): Promise<MessageResponse> {
  return apiClient.post<MessageResponse>("/api/v1/users/me/change-email", body);
}

export function confirmEmailChange(token: string): Promise<UserPublic> {
  return apiClient.post<UserPublic>(
    "/api/v1/users/confirm-email-change",
    { token },
    { auth: false },
  );
}

export function deleteAccount(password: string): Promise<void> {
  return apiClient.delete<void>("/api/v1/users/me", { password, confirm: true });
}
