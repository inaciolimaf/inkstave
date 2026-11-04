/**
 * The main-thread side of the spell worker (spec 113): one worker per tab, created on the first request,
 * so a project with spell check off never starts it. Every request has a deadline, and a worker that
 * fails rejects what is pending; the next request starts a fresh one.
 */
import type { SpellOperation, SpellRequest, SpellResponse } from "./spell-protocol";
import type { SpellChecker } from "./types";

const DEADLINE_MS = 15_000;

interface Pending {
  resolve: (result: string[]) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

let worker: Worker | null = null;
let nextId = 1;
const pending = new Map<number, Pending>();

function settle(response: SpellResponse): void {
  const entry = pending.get(response.id);
  if (!entry) return; // Answered after its deadline.
  pending.delete(response.id);
  clearTimeout(entry.timer);
  if (response.ok) entry.resolve(response.result);
  else entry.reject(new Error(response.error));
}

function failAll(error: Error): void {
  for (const [id, entry] of pending) {
    clearTimeout(entry.timer);
    entry.reject(error);
    pending.delete(id);
  }
}

function ensureWorker(): Worker {
  if (worker) return worker;
  const created = new Worker(new URL("./spell.worker.ts", import.meta.url), { type: "module" });
  created.onmessage = (event: MessageEvent<SpellResponse>) => settle(event.data);
  created.onerror = () => {
    failAll(new Error("The spell-check worker failed."));
    created.terminate();
    if (worker === created) worker = null;
  };
  worker = created;
  return created;
}

function request(operation: SpellOperation): Promise<string[]> {
  return new Promise((resolve, reject) => {
    let target: Worker;
    try {
      target = ensureWorker();
    } catch (error) {
      reject(error instanceof Error ? error : new Error(String(error)));
      return;
    }
    const id = nextId++;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error("The spell check did not answer in time."));
    }, DEADLINE_MS);
    pending.set(id, { resolve, reject, timer });
    const message: SpellRequest = { ...operation, id, base: import.meta.env.BASE_URL };
    target.postMessage(message);
  });
}

/** The checker the editor uses in the browser. */
export const workerSpellChecker: SpellChecker = {
  check: (language, words) => request({ op: "check", language, words }),
  suggest: (language, word) => request({ op: "suggest", language, word }),
};
