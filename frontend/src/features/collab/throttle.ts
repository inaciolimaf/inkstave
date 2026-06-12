/** Leading+trailing throttle: collapse a burst of calls into bounded invocations. */
export interface Throttled<A extends unknown[]> {
  (...args: A): void;
  cancel: () => void;
}

export function throttle<A extends unknown[]>(fn: (...args: A) => void, ms: number): Throttled<A> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pending = false;
  let lastArgs: A | null = null;

  const wrapped = ((...args: A) => {
    lastArgs = args;
    if (timer === null) {
      fn(...args); // leading edge
      timer = setTimeout(() => {
        timer = null;
        if (pending && lastArgs) {
          pending = false;
          wrapped(...lastArgs); // trailing edge with the latest args
        }
      }, ms);
    } else {
      pending = true; // collapse intermediate calls
    }
  }) as Throttled<A>;

  wrapped.cancel = () => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
    pending = false;
    lastArgs = null;
  };

  return wrapped;
}
