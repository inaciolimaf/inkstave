import { isolateHistory } from "@codemirror/commands";
import type { EditorView } from "@codemirror/view";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

import { insertSnippet } from "../insert-text";

import { mathAt, wrapMath, type MathRegion } from "./find-math";
import { loadMathLive } from "./mathlive-loader";
import { MathField } from "./math-field";

type LoadState = "loading" | "ready" | "failed";

/** Loads MathLive once the dialog opens. A failure leaves the state "failed", and the dialog then uses a textarea. */
function useMathLive(): LoadState {
  const [state, setState] = useState<LoadState>("loading");
  useEffect(() => {
    let alive = true;
    loadMathLive().then(
      () => {
        if (alive) setState("ready");
      },
      () => {
        if (alive) setState("failed");
      },
    );
    return () => {
      alive = false;
    };
  }, []);
  return state;
}

/** Touch devices show MathLive's keyboard by default; a desktop shows it only when asked. */
function isTouchDevice(): boolean {
  return window.matchMedia?.("(pointer: coarse)").matches === true;
}

/** Replaces the body of the math the cursor is in, or inserts new math at the cursor. */
function applyEdit(view: EditorView, target: MathRegion | null, latex: string, display: boolean) {
  if (!target) {
    insertSnippet(view, wrapMath(latex, display));
    return;
  }
  view.dispatch({
    changes: { from: target.from, to: target.to, insert: latex },
    selection: { anchor: target.from + latex.length },
    annotations: isolateHistory.of("full"),
  });
}

function EditorBody({
  state,
  latex,
  onChange,
  keyboard,
  label,
}: {
  state: LoadState;
  latex: string;
  onChange: (latex: string) => void;
  keyboard: boolean;
  label: string;
}) {
  const { t } = useTranslation("insert");
  if (state === "loading") {
    return (
      <div role="status" className="flex items-center gap-2 py-6 text-body text-muted-foreground">
        <Loader2 aria-hidden="true" className="size-4 animate-spin" />
        {t("equation.loading")}
      </div>
    );
  }
  if (state === "failed") {
    return (
      <Textarea
        aria-label={t("equation.fallbackLabel")}
        value={latex}
        onChange={(event) => onChange(event.target.value)}
        className="font-mono text-small"
      />
    );
  }
  return <MathField initial={latex} label={label} keyboard={keyboard} onChange={onChange} />;
}

/**
 * The equation editor (spec 114 §5.4). It opens on the math under the cursor, or empty. Save writes the LaTeX
 * back as one undoable edit; Cancel changes nothing.
 */
export function EquationDialog({ view, onClose }: { view: EditorView; onClose: () => void }) {
  const { t } = useTranslation("insert");
  const [target] = useState(() => mathAt(view.state.doc.toString(), view.state.selection.main.head));
  const [latex, setLatex] = useState(target?.latex ?? "");
  const [display, setDisplay] = useState(false);
  const [keyboard, setKeyboard] = useState(isTouchDevice);
  const state = useMathLive();
  const save = () => {
    applyEdit(view, target, latex, display);
    onClose();
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("equation.title")}</DialogTitle>
          <DialogDescription>{t("equation.description")}</DialogDescription>
        </DialogHeader>
        <EditorBody
          state={state}
          latex={latex}
          onChange={setLatex}
          keyboard={keyboard}
          label={t("equation.fallbackLabel")}
        />
        <div className="flex flex-wrap items-center gap-4 text-small">
          {!target && (
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={display}
                onChange={(event) => setDisplay(event.target.checked)}
                className="size-4 accent-foreground"
              />
              {t("equation.display")}
            </label>
          )}
          {state === "ready" && (
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={keyboard}
                onChange={(event) => setKeyboard(event.target.checked)}
                className="size-4 accent-foreground"
              />
              {t("equation.keyboard")}
            </label>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("equation.cancel")}
          </Button>
          <Button onClick={save} disabled={!target && latex.trim() === ""}>
            {t("equation.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
