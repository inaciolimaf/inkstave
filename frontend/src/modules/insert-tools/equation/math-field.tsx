import { useEffect, useRef } from "react";

/** The part of MathLive's `<math-field>` the dialog uses. Its value is the LaTeX of the formula. */
interface MathFieldLike extends HTMLElement {
  value: string;
  mathVirtualKeyboardPolicy: "auto" | "manual" | "sandboxed";
}

/**
 * The visual formula editor. It creates the element itself, once MathLive is loaded, so the dialog never renders
 * a custom element that is not defined yet. `onChange` gets the LaTeX after each edit.
 */
export function MathField({
  initial,
  label,
  keyboard,
  onChange,
}: {
  initial: string;
  label: string;
  keyboard: boolean;
  onChange: (latex: string) => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<MathFieldLike | null>(null);
  const changeRef = useRef(onChange);
  changeRef.current = onChange;

  useEffect(() => {
    const field = document.createElement("math-field") as MathFieldLike;
    field.value = initial;
    field.addEventListener("input", () => changeRef.current(field.value));
    hostRef.current?.append(field);
    fieldRef.current = field;
    return () => field.remove();
    // The field is created once; later values flow through `onChange`, and a new value would reset the cursor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const field = fieldRef.current;
    if (!field) return;
    field.mathVirtualKeyboardPolicy = keyboard ? "auto" : "manual";
    if (keyboard) window.mathVirtualKeyboard?.show();
    else window.mathVirtualKeyboard?.hide();
  }, [keyboard]);

  return (
    <div
      ref={hostRef}
      role="group"
      aria-label={label}
      className="min-h-16 rounded-md border bg-background px-3 py-2 text-heading [&_math-field]:w-full"
    />
  );
}
