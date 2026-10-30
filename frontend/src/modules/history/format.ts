/** Small formatting helpers for the history UI (spec 38). */
import i18n from "@/i18n/config";

const _UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 60 * 60 * 24 * 365],
  ["month", 60 * 60 * 24 * 30],
  ["day", 60 * 60 * 24],
  ["hour", 60 * 60],
  ["minute", 60],
  ["second", 1],
];

/** "2 hours ago" style relative time for an ISO timestamp. Localised at call time. */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const rtf = new Intl.RelativeTimeFormat(i18n.language, { numeric: "auto" });
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const abs = Math.abs(seconds);
  for (const [unit, secs] of _UNITS) {
    if (abs >= secs || unit === "second") {
      return rtf.format(Math.round(seconds / secs), unit);
    }
  }
  return rtf.format(0, "second");
}

/** Absolute ISO-ish time for the tooltip. */
export function absoluteTime(iso: string): string {
  return new Date(iso).toISOString();
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
