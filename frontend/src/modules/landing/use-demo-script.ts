import { useEffect, useRef, useState } from "react";

import { reducedMotion } from "@/lib/motion";

export type Phase = "prompt" | "reading" | "reply" | "diff" | "applying" | "applied";

export interface DemoState {
  phase: Phase;
  typed: number; // chars of the prompt revealed
  chips: number; // tool chips shown (0–2)
}

/** Plays the agent demo's timed script on a loop; reduced motion rests on the "applied" state. */
export function useDemoScript(prompt: string): DemoState {
  const [state, setState] = useState<DemoState>({ phase: "prompt", typed: 0, chips: 0 });
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (reducedMotion()) {
      setState({ phase: "applied", typed: prompt.length, chips: 2 });
      return;
    }

    const queue = timers.current;
    const after = (ms: number, fn: () => void) => queue.push(setTimeout(fn, ms));

    const runCycle = () => {
      setState({ phase: "prompt", typed: 0, chips: 0 });

      // 1. Type the prompt out, char by char.
      const typeStep = (i: number) => {
        setState((s) => ({ ...s, typed: i }));
        if (i < prompt.length) {
          after(34, () => typeStep(i + 1));
        } else {
          after(520, beginReading);
        }
      };

      // 2. Agent searches, then reads.
      const beginReading = () => {
        setState((s) => ({ ...s, phase: "reading", chips: 1 }));
        after(820, () => setState((s) => ({ ...s, chips: 2 })));
        after(1700, beginReply);
      };

      // 3. Agent replies, then 4. shows the diff.
      const beginReply = () => {
        setState((s) => ({ ...s, phase: "reply" }));
        after(900, () => setState((s) => ({ ...s, phase: "diff" })));
        after(2700, accept);
      };

      // 5. Accept → 6. applied, then loop.
      const accept = () => {
        setState((s) => ({ ...s, phase: "applying" }));
        after(560, () => setState((s) => ({ ...s, phase: "applied" })));
        after(3800, runCycle);
      };

      typeStep(0);
    };

    runCycle();
    return () => {
      queue.forEach(clearTimeout);
      queue.length = 0;
    };
  }, [prompt]);

  return state;
}
