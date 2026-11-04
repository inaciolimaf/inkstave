/** Spell-check API calls (spec 113): the project language and the personal dictionary. */
import type { Schemas } from "@/api/models";
import { apiClient } from "@/lib/api-client";

import type { SpellLanguage } from "./types";

export function listDictionary(): Promise<string[]> {
  return apiClient.get<Schemas["DictionaryList"]>("/api/v1/me/dictionary").then((list) => list.words);
}

export async function addDictionaryWord(word: string): Promise<void> {
  await apiClient.post("/api/v1/me/dictionary", { word });
}

export async function removeDictionaryWord(word: string): Promise<void> {
  await apiClient.delete(`/api/v1/me/dictionary/${encodeURIComponent(word)}`);
}

export async function updateSpellcheckLanguage(
  projectId: string,
  language: SpellLanguage,
): Promise<SpellLanguage> {
  const project = await apiClient.patch<Schemas["ProjectRead"]>(`/api/v1/projects/${projectId}/settings`, {
    spellcheck_language: language,
  });
  return project.spellcheck_language;
}
