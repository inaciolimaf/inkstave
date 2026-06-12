import { ApiError } from "@/lib/api-client";

export function errMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.fieldErrors) return Object.values(e.fieldErrors)[0] ?? e.message;
    return e.message;
  }
  return "Something went wrong.";
}
