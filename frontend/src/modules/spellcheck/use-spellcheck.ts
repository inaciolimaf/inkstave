import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api-client";
import { getProject, projectKey } from "@/modules/projects";
import i18n from "@/i18n/config";

import { addDictionaryWord, listDictionary, removeDictionaryWord, updateSpellcheckLanguage } from "./api";
import { workerSpellChecker } from "./spell-client";
import { isDictionaryLanguage, type SpellcheckBinding, type SpellLanguage } from "./types";

export const DICTIONARY_KEY = ["spellcheck", "dictionary"] as const;

/** The project's spell-check language, and a setter for members who may write documents. */
export function useSpellLanguage(projectId: string) {
  const qc = useQueryClient();
  const project = useQuery({ queryKey: projectKey(projectId), queryFn: () => getProject(projectId) });
  const save = useMutation({
    mutationFn: (language: SpellLanguage) => updateSpellcheckLanguage(projectId, language),
    onSuccess: (language) => {
      qc.setQueryData(projectKey(projectId), (old: Awaited<ReturnType<typeof getProject>> | undefined) =>
        old ? { ...old, spellcheckLanguage: language } : old,
      );
    },
    onError: () => toast.error(i18n.t("editor:spellcheck.saveFailed")),
  });
  return {
    language: (project.data?.spellcheckLanguage ?? "off") as SpellLanguage,
    setLanguage: save.mutate,
    saving: save.isPending,
  };
}

function dictionaryError(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return i18n.t("editor:spellcheck.dictionaryFull");
  return i18n.t("editor:spellcheck.dictionaryFailed");
}

/** The signed-in user's personal dictionary, fetched only while a language is on. */
export function usePersonalDictionary(enabled = true) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: DICTIONARY_KEY, queryFn: listDictionary, enabled });

  const add = useMutation({
    mutationFn: addDictionaryWord,
    onMutate: async (word: string) => {
      await qc.cancelQueries({ queryKey: DICTIONARY_KEY });
      const previous = qc.getQueryData<string[]>(DICTIONARY_KEY);
      if (previous) qc.setQueryData<string[]>(DICTIONARY_KEY, [...previous, word]);
      return { previous };
    },
    onError: (error, _word, context) => {
      qc.setQueryData(DICTIONARY_KEY, context?.previous);
      toast.error(dictionaryError(error));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: DICTIONARY_KEY }),
  });

  const remove = useMutation({
    mutationFn: removeDictionaryWord,
    onMutate: async (word: string) => {
      await qc.cancelQueries({ queryKey: DICTIONARY_KEY });
      const previous = qc.getQueryData<string[]>(DICTIONARY_KEY);
      const lower = word.toLowerCase();
      if (previous)
        qc.setQueryData<string[]>(
          DICTIONARY_KEY,
          previous.filter((w) => w.toLowerCase() !== lower),
        );
      return { previous };
    },
    onError: (error, _word, context) => {
      qc.setQueryData(DICTIONARY_KEY, context?.previous);
      toast.error(dictionaryError(error));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: DICTIONARY_KEY }),
  });

  return {
    words: query.data,
    isLoading: query.isPending,
    isError: query.isError,
    add: add.mutate,
    remove: remove.mutate,
  };
}

const ignoreKey = (documentId: string) => `inkstave:spellcheck-ignore:${documentId}`;

/** Words ignored in one document. Kept in `localStorage`, so a blocked store only forgets them. */
function readIgnored(documentId: string): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(ignoreKey(documentId)) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((w): w is string => typeof w === "string") : [];
  } catch {
    return [];
  }
}

function writeIgnored(documentId: string, words: string[]): void {
  try {
    localStorage.setItem(ignoreKey(documentId), JSON.stringify(words));
  } catch {
    /* A blocked store keeps the words for this view only. */
  }
}

export function useIgnoredWords(documentId: string | null) {
  const [version, setVersion] = useState(0);
  const words = useMemo(
    () => new Set(documentId ? readIgnored(documentId) : []),
    // `version` changes when a word is ignored, so the set is read again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [documentId, version],
  );
  const add = useCallback(
    (word: string) => {
      if (!documentId) return;
      const lower = word.toLowerCase();
      const current = readIgnored(documentId);
      if (!current.includes(lower)) writeIgnored(documentId, [...current, lower]);
      setVersion((v) => v + 1);
    },
    [documentId],
  );
  return { words, add };
}

export interface SpellcheckState {
  /** Null while the check is off or its dictionary words have not loaded. */
  binding: SpellcheckBinding | null;
  /** The dictionary of the current language could not be loaded. */
  failed: boolean;
}

/** Everything one open document needs from spell checking (spec 113). */
export function useSpellcheck(projectId: string, documentId: string | null): SpellcheckState {
  const { language } = useSpellLanguage(projectId);
  const dictionary = usePersonalDictionary(language !== "off");
  const ignored = useIgnoredWords(documentId);
  const [failedLanguage, setFailedLanguage] = useState<SpellLanguage | null>(null);
  const { add: addToDictionary } = dictionary;
  const { add: ignore } = ignored;
  const personal = dictionary.words;
  const binding = useMemo<SpellcheckBinding | null>(() => {
    if (!isDictionaryLanguage(language) || !personal) return null;
    const known = new Set(personal.map((w) => w.toLowerCase()));
    return {
      language,
      checker: workerSpellChecker,
      accepts: (word) => {
        const lower = word.toLowerCase();
        return known.has(lower) || ignored.words.has(lower);
      },
      addToDictionary: (word) => addToDictionary(word),
      ignoreInDocument: (word) => ignore(word),
      reportFailure: () => setFailedLanguage(language),
    };
  }, [language, personal, ignored.words, addToDictionary, ignore]);
  return { binding, failed: failedLanguage !== null && failedLanguage === language };
}
