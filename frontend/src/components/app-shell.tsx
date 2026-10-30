/** Around every screen: the skip link, the document title, and focus after a route change. */
import { type MouseEvent, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation, useMatches } from "react-router-dom";

const APP_NAME = "Inkstave";

/** Programmatic focus: not in the tab order, no outline, and no leftover tabindex once it leaves. */
function focusQuietly(element: HTMLElement) {
  element.tabIndex = -1;
  element.style.outline = "none";
  element.addEventListener("blur", () => element.removeAttribute("tabindex"), { once: true });
  element.focus();
}

function focusMain() {
  const main = document.querySelector<HTMLElement>("main");
  if (main) focusQuietly(main);
}

function focusScreen() {
  const heading = document.querySelector<HTMLElement>("h1");
  if (heading) focusQuietly(heading);
  else focusMain();
}

function skipToMain(event: MouseEvent) {
  event.preventDefault(); // the URL keeps no hash, and the router sees no navigation
  focusMain();
}

/** The `common` key of the deepest route that declares a title. */
function useTitleKey(): string | undefined {
  const titles = useMatches().map((match) => (match.handle as { title?: string } | undefined)?.title);
  return titles.filter(Boolean).at(-1);
}

function useDocumentTitle() {
  const { t } = useTranslation("common");
  const key = useTitleKey();
  const staticTitle = useRef(document.title); // index.html's, which the landing keeps

  useEffect(() => {
    document.title = key ? `${t(key)} — ${APP_NAME}` : staticTitle.current;
  }, [key, t]);
}

/** A screen reader hears nothing after a client-side navigation unless focus moves. */
function useFocusOnNavigation() {
  const { pathname } = useLocation();
  const previous = useRef(pathname);

  useEffect(() => {
    if (previous.current === pathname) return; // the first load
    previous.current = pathname;
    focusScreen();
  }, [pathname]);
}

export function AppShell() {
  const { t } = useTranslation("common");
  useDocumentTitle();
  useFocusOnNavigation();

  return (
    <>
      <a
        href="#main"
        onClick={skipToMain}
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-body focus:text-foreground focus:shadow"
      >
        {t("shell.skipToContent")}
      </a>
      <Outlet />
    </>
  );
}
