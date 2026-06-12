import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import { landingEn, landingPt } from "@/features/landing/i18n";

import enAgent from "./locales/en/agent";
import enAuth from "./locales/en/auth";
import enCommon from "./locales/en/common";
import enEditor from "./locales/en/editor";
import enFiles from "./locales/en/files";
import enHistory from "./locales/en/history";
import enNotifications from "./locales/en/notifications";
import enPreview from "./locales/en/preview";
import enProjects from "./locales/en/projects";
import enReview from "./locales/en/review";
import enSettings from "./locales/en/settings";
import enSharing from "./locales/en/sharing";
import ptAgent from "./locales/pt/agent";
import ptAuth from "./locales/pt/auth";
import ptCommon from "./locales/pt/common";
import ptEditor from "./locales/pt/editor";
import ptFiles from "./locales/pt/files";
import ptHistory from "./locales/pt/history";
import ptNotifications from "./locales/pt/notifications";
import ptPreview from "./locales/pt/preview";
import ptProjects from "./locales/pt/projects";
import ptReview from "./locales/pt/review";
import ptSettings from "./locales/pt/settings";
import ptSharing from "./locales/pt/sharing";

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
  "settings",
  "sharing",
  "notifications",
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
    settings: enSettings,
    sharing: enSharing,
    notifications: enNotifications,
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
    settings: ptSettings,
    sharing: ptSharing,
    notifications: ptNotifications,
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
