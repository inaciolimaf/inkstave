/** Mirrors spec 12's name rules for friendly client-side pre-validation. */
export function validateEntityName(raw: string): string | null {
  const name = raw.trim();
  if (!name) return "Name is required.";
  if (name.length > 255) return "Name must be at most 255 characters.";
  if (name === "." || name === "..") return "Name cannot be \u201c.\u201d or \u201c..\u201d.";
  if (/[/\\]/.test(name)) return "Name cannot contain slashes.";
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f]/.test(name)) return "Name cannot contain control characters.";
  return null;
}
