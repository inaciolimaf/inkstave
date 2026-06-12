import i18n from "@/i18n/config";
import { ApiError } from "@/lib/api-client";

export function errMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.fieldErrors) return Object.values(e.fieldErrors)[0] ?? e.message;
    return e.message;
  }
  return i18n.t("settings:error.generic");
}
