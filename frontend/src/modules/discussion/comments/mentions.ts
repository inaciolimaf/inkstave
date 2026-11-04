/**
 * `@` mentions in a comment (spec 118). The body shows `@Name`; what the server receives is the list of
 * ids the author picked, and a pick counts only while its `@Name` is still in the text.
 */

export interface MentionCandidate {
  id: string;
  name: string;
}

/** The ids of the picked members whose `@Name` is still in the body. */
export function mentionIds(body: string, picked: MentionCandidate[]): string[] {
  const ids = picked.filter((candidate) => body.includes(`@${candidate.name}`)).map((c) => c.id);
  return [...new Set(ids)];
}

export interface MentionQuery {
  /** Index of the `@` that starts the query. */
  start: number;
  query: string;
}

/** The `@` word the caret is in, if the caret is right after one. */
export function mentionQuery(value: string, caret: number): MentionQuery | null {
  const match = /(^|\s)@([^\s@]*)$/.exec(value.slice(0, caret));
  if (!match) return null;
  const query = match[2] ?? "";
  return { start: caret - query.length - 1, query };
}

/** The text with the `@query` at `start` replaced by `@Name `, and the caret after it. */
export function insertMention(
  value: string,
  caret: number,
  start: number,
  name: string,
): { value: string; caret: number } {
  const inserted = `@${name} `;
  return {
    value: value.slice(0, start) + inserted + value.slice(caret),
    caret: start + inserted.length,
  };
}

/** The members whose name matches the query, case-insensitively, names starting with it first. */
export function matchingMembers(members: MentionCandidate[], query: string): MentionCandidate[] {
  const wanted = query.toLocaleLowerCase();
  const matches = members.filter((m) => m.name.toLocaleLowerCase().includes(wanted));
  return matches.sort((a, b) => {
    const aStarts = a.name.toLocaleLowerCase().startsWith(wanted) ? 0 : 1;
    const bStarts = b.name.toLocaleLowerCase().startsWith(wanted) ? 0 : 1;
    return aStarts - bStarts || a.name.localeCompare(b.name);
  });
}
