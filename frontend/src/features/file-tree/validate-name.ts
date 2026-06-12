import i18n from "@/i18n/config";

/** Mirrors spec 12's name rules for friendly client-side pre-validation. */
export function validateEntityName(raw: string): string | null {
  const name = raw.trim();
  if (!name) return i18n.t("files:validate.required");
  if (name.length > 255) return i18n.t("files:validate.tooLong");
  if (name === "." || name === "..") return i18n.t("files:validate.reserved");
  if (/[/\\]/.test(name)) return i18n.t("files:validate.slashes");
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f]/.test(name)) return i18n.t("files:validate.control");
  return null;
}
