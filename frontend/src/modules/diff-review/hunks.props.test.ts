/** Property tests for the review edit model (spec 47): applying the minimal edit gives the target. */
import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { minimalEdit } from "./hunks";

const text = fc.stringMatching(/^[ab\né]{0,30}$/);

describe("review edit properties", () => {
  it("the minimal edit turns the current text into the target, and touches one region only", () => {
    fc.assert(
      fc.property(text, text, (current, target) => {
        const { start, deleteLength, insert } = minimalEdit(current, target);
        const applied = current.slice(0, start) + insert + current.slice(start + deleteLength);
        expect(applied).toBe(target);
        expect(start + deleteLength).toBeLessThanOrEqual(current.length);
      }),
      { numRuns: 100 },
    );
  });
});
