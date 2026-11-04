/** The spell-check module: underlines misspelled words and offers suggestions (spec 113). */
export { SpellMenu, type SpellMenuState } from "./spell-menu";
export { SpellingMenuItems } from "./spelling-menu-items";
export { misspelledAt, spellcheckFor, type MisspelledWord } from "./spellcheck-extension";
export { useSpellcheck, usePersonalDictionary, type SpellcheckState } from "./use-spellcheck";
export { SPELL_LANGUAGES, type SpellLanguage, type SpellcheckBinding } from "./types";
