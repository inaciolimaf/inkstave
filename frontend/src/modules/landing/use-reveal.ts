import { useEffect, useRef } from "react";

/**
 * Adds `is-visible` to an element the first time it scrolls into view, driving
 * the CSS `.reveal` transition. One-shot per element (we unobserve after the
 * first intersection) so content never re-animates while the user scrolls back
 * and forth. Falls back to immediately-visible when IntersectionObserver is
 * unavailable (e.g. jsdom in unit tests).
 */
export function useReveal<T extends HTMLElement = HTMLElement>() {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    if (typeof IntersectionObserver === "undefined") {
      node.classList.add("is-visible");
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.18, rootMargin: "0px 0px -8% 0px" },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return ref;
}
