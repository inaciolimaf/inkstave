# Spec 115 — Speak to the agent (requirements)

## 1. Summary
Competitors let a writer say "change the title of section 2 to Methods". Inkstave already has an agent that turns
such a request into a reviewable proposal, so voice only has to produce the text. This spec uses the browser's
`SpeechRecognition` and adds no server code, no new dependency and no audio storage.

## 2. Context & dependencies
- **Depends on:** 46 (agent panel), 107 (panel layout), 110 (inline review of the result).
- **Affected areas:** frontend `agent`; docs.

## 3. Goals
- A microphone button next to the agent's send button, shown only where `SpeechRecognition` or
  `webkitSpeechRecognition` exists.
- Press to start, press again (or 2 s of silence) to stop. While listening: a pulsing state, interim words shown in
  the message box in a muted style, final words in normal style.
- The transcript lands in the message box; it is **not** sent automatically. The user can edit and send, or press
  Escape to discard. A preference "Send after dictation" (default off) sends at once when the recognition ends.
- Recognition language follows the interface language (`en-US` or `pt-BR`), with a menu on the button to switch.
- On-device first: where the browser exposes `SpeechRecognition.available({langs, processLocally: true})` and it
  answers available, set `processLocally = true`. Otherwise, the browser may send audio to its vendor's service:
  before the first use, show a one-time notice saying so ("Your browser may send the audio to its speech
  service (for Chrome, Google). Inkstave never receives the audio.") with Continue / Cancel. The choice is kept in
  `localStorage`.
- Errors (`not-allowed`, `no-speech`, `network`, `audio-capture`) become a short message under the box in plain
  words, never a dialog.

## 4. Non-goals
- Dictating into the document itself.
- Server-side speech-to-text, recording or storing audio.
- Voice output (reading the reply aloud).

## 5. Detailed requirements
- `frontend/src/modules/agent/voice/`:
  - `speech.ts`: a thin wrapper, `createRecognizer({lang, onInterim, onFinal, onEnd, onError})`, the only file that
    touches the browser API, so tests replace it.
  - `use-dictation.ts`: the state machine `idle → asking-consent → listening → idle`, with stop on silence, and
    cleanup on unmount and when the panel folds.
  - `mic-button.tsx`: the button with `aria-pressed`, label "Dictate" / "Stop dictating" (PT "Ditar" / "Parar
    ditado"), and the language menu.
- The microphone permission prompt is the browser's; Inkstave never calls `getUserMedia` itself.
- Keyboard: `Ctrl/Cmd+Shift+M` toggles dictation while the agent panel has focus.
- Phone: the button is at least 44 px and stays inside the sheet's input row at 390 px.
- Viewers keep the button: they may talk to the agent (read tools only). It is enabled exactly when the send
  button is.
- All strings in `en` and `pt` (`agent` namespace).

## 6. Overleaf reference
No equivalent.

## 7. Acceptance criteria
1. In a browser without `SpeechRecognition` (Firefox), no microphone appears and nothing errors.
2. Speaking "troque o título da seção dois para Métodos" with the PT interface fills the box with that sentence;
   sending it starts a normal run whose result is a proposal reviewed inline (spec 110).
3. Without on-device support, the first press shows the notice; Cancel starts nothing.
4. Denying the microphone shows "Microphone access was blocked." and the button returns to idle.
5. Folding the agent panel while listening stops recognition.

## 8. Test plan
- **Vitest:** `use-dictation` with a fake recognizer: interim and final text, silence stop, consent path, each error
  code, unmount cleanup; feature detection hides the button; `processLocally` chosen when available; the
  "send after dictation" preference.
- **Budget:** no browser speech in tests.

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| Inkstave never receives or stores audio | `speech.ts` is the only API user and sends text only; `speech.test.ts` |
| Dictation never sends a message unless the user chose it | `use-dictation.test.ts` |
| Cloud recognition needs the user's consent first | `use-dictation.test.ts` |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 green.
- [ ] `docs/system/frontend.md` and `docs/user-guide.md` describe dictation and its privacy notice.
- [ ] Glossary: "Dictation" → `use-dictation` → "Ditado".
