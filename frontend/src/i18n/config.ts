import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import { landingEn, landingPt } from "@/i18n/locales/landing";

import enAgent from "./locales/en/agent";
import enAuth from "./locales/en/auth";
import enCommon from "./locales/en/common";
import enDiscussion from "./locales/en/discussion";
import enEditor from "./locales/en/editor";
import enFiles from "./locales/en/files";
import enHistory from "./locales/en/history";
import enInsert from "./locales/en/insert";
import enNotifications from "./locales/en/notifications";
import enPreview from "./locales/en/preview";
import enProjects from "./locales/en/projects";
import enReview from "./locales/en/review";
import enSettings from "./locales/en/settings";
import enSharing from "./locales/en/sharing";
import enSearch from "./locales/en/search";
import enSuggest from "./locales/en/suggest";
import ptAgent from "./locales/pt/agent";
import ptAuth from "./locales/pt/auth";
import ptCommon from "./locales/pt/common";
import ptDiscussion from "./locales/pt/discussion";
import ptEditor from "./locales/pt/editor";
import ptFiles from "./locales/pt/files";
import ptHistory from "./locales/pt/history";
import ptInsert from "./locales/pt/insert";
import ptNotifications from "./locales/pt/notifications";
import ptPreview from "./locales/pt/preview";
import ptProjects from "./locales/pt/projects";
import ptReview from "./locales/pt/review";
import ptSettings from "./locales/pt/settings";
import ptSharing from "./locales/pt/sharing";
import ptSearch from "./locales/pt/search";
import ptSuggest from "./locales/pt/suggest";

/*
 * Global i18n for the whole app. English is the default; a Portuguese-language
 * browser (pt-BR, pt-PT…) gets Portuguese, collapsed to "pt" by
 * `load: "languageOnly"`. Detection is by navigator language. Strings are split
 * into one namespace per feature area so they stay organised and easy to grow.
 */

export const NAMESPACES = [
  "common",
  "landing",
  "auth",
  "projects",
  "editor",
  "files",
  "preview",
  "agent",
  "review",
  "history",
  "insert",
  "settings",
  "sharing",
  "notifications",
  "discussion",
  "suggest",
  "search",
] as const;

const resources = {
  en: {
    common: enCommon,
    landing: landingEn,
    auth: enAuth,
    projects: enProjects,
    editor: enEditor,
    files: enFiles,
    preview: enPreview,
    agent: enAgent,
    review: enReview,
    history: enHistory,
    insert: enInsert,
    settings: enSettings,
    sharing: enSharing,
    notifications: enNotifications,
    discussion: enDiscussion,
    suggest: enSuggest,
    search: enSearch,
  },
  pt: {
    common: ptCommon,
    landing: landingPt,
    auth: ptAuth,
    projects: ptProjects,
    editor: ptEditor,
    files: ptFiles,
    preview: ptPreview,
    agent: ptAgent,
    review: ptReview,
    history: ptHistory,
    insert: ptInsert,
    settings: ptSettings,
    sharing: ptSharing,
    notifications: ptNotifications,
    discussion: ptDiscussion,
    suggest: ptSuggest,
    search: ptSearch,
  },
};

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: "en",
    supportedLngs: ["en", "pt"],
    load: "languageOnly",
    ns: NAMESPACES,
    defaultNS: "common",
    detection: { order: ["navigator", "htmlTag"], caches: [] },
    interpolation: { escapeValue: false },
    returnNull: false,
  });

// Keep <html lang> in sync for accessibility and correct hyphenation.
const applyLang = (lng: string) => {
  document.documentElement.lang = lng.split("-")[0];
};
applyLang(i18n.language || "en");
i18n.on("languageChanged", applyLang);

export default i18n;
