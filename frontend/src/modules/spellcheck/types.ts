/** The spell-check languages a project can use (spec 113). `off` loads nothing. */
export const SPELL_LANGUAGES = ["off", "en-US", "pt-BR"] as const;
export type SpellLanguage = (typeof SPELL_LANGUAGES)[number];

/** Languages with a dictionary file under `public/dictionaries/`: `<language>.aff` and `.dic`. */
export const DICTIONARY_LANGUAGES = ["en-US", "pt-BR"] as const;
export type DictionaryLanguage = (typeof DICTIONARY_LANGUAGES)[number];

export const MAX_SUGGESTIONS = 5;

/** A word of the text, by document offsets. */
export interface CheckableWord {
  from: number;
  to: number;
  word: string;
}

/** What the editor needs from a spell checker. The worker implements it; tests pass a fake. */
export interface SpellChecker {
  /** The subset of `words` that the dictionary does not know. */
  check(language: DictionaryLanguage, words: string[]): Promise<string[]>;
  suggest(language: DictionaryLanguage, word: string): Promise<string[]>;
}

/** What one open document needs from the spell check: its language, the words the user keeps and actions. */
export interface SpellcheckBinding {
  language: DictionaryLanguage;
  checker: SpellChecker;
  /** True for the personal dictionary and this document's ignore list (lowercase comparison). */
  accepts: (word: string) => boolean;
  addToDictionary: (word: string) => void;
  ignoreInDocument: (word: string) => void;
  /** Tells the binding that the dictionary could not be loaded. */
  reportFailure: () => void;
}

export function isDictionaryLanguage(value: string): value is DictionaryLanguage {
  return (DICTIONARY_LANGUAGES as readonly string[]).includes(value);
}
