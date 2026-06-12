/** Trigger a browser "Save as" for an in-memory blob via a temporary anchor. */
export function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Sanitize a project name into a safe download filename stem (no path/quote/control chars). */
export function sanitizeDownloadName(name: string): string {
  const cleaned = Array.from(name)
    .map((ch) => (ch.charCodeAt(0) < 0x20 || ch === "/" || ch === "\\" || ch === '"' ? " " : ch))
    .join("")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned || "project";
}
