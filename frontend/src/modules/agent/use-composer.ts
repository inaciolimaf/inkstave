/** The message box's state: the draft, the quoted selection, dictation and the keys that drive them (spec 115). */
import type { KeyboardEvent } from "react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { type AgentQuote, withQuote } from "./quote";
import { appendSpoken, isDictationShortcut, useDictation } from "./voice/use-dictation";

export function useComposer({
  open,
  busy,
  send,
  onClose,
}: {
  open: boolean;
  /** A run is in progress: the box is locked and dictation cannot start. */
  busy: boolean;
  send: (text: string) => Promise<boolean>;
  onClose: () => void;
}) {
  const { i18n } = useTranslation("agent");
  const [text, setTextState] = useState("");
  const [quote, setQuote] = useState<AgentQuote | null>(null);
  // A dictation event reads the draft as it is right then, not as the last render saw it.
  const draftRef = useRef("");
  const draftAtStart = useRef("");

  const setText = (next: string) => {
    draftRef.current = next;
    setTextState(next);
  };

  const sendText = (typed: string) => {
    const sentQuote = quote;
    setText("");
    setQuote(null);
    void send(withQuote(typed, sentQuote)).then((accepted) => {
      if (accepted) return;
      setText(typed);
      setQuote(sentQuote);
    });
  };

  const dictation = useDictation({
    active: open,
    busy,
    interfaceLang: i18n.language,
    onStart: () => {
      draftAtStart.current = draftRef.current;
    },
    onFinal: (spoken) => setText(appendSpoken(draftRef.current, spoken)),
    onEnd: ({ heard, sendAfter }) => {
      const typed = draftRef.current.trim();
      if (heard && sendAfter && typed) sendText(typed);
    },
  });

  /** A send ends listening at once; the words said so far are already in the box. */
  const sendTyped = (typed: string) => {
    dictation.cancel();
    sendText(typed);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (dictation.supported && isDictationShortcut(e)) {
      e.preventDefault();
      dictation.toggle();
    } else if (e.key === "Escape" && e.currentTarget.contains(e.target as Node)) {
      // Escape while dictating drops what this session put in the box; otherwise it folds the panel.
      if (dictation.state !== "listening") onClose();
      else {
        dictation.cancel();
        setText(draftAtStart.current);
      }
    }
  };

  return { text, setText, quote, setQuote, dictation, sendTyped, onKeyDown };
}
