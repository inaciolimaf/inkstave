/** The only place that formats numbers and dates for people; uses the browser's locale. */

export function formatNumber(value: number): string {
  return value.toLocaleString();
}

/** e.g. "Mar 4, 2026". */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString();
}
