import { describe, expect, it } from "vitest";

import { formatDate, formatDateTime, formatNumber } from "./formatting";

describe("formatting", () => {
  it("formats a date with the year, short month and day", () => {
    const iso = "2026-03-04T12:00:00Z";
    expect(formatDate(iso)).toBe(
      new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }),
    );
  });

  it("formats a date and time in the locale's default style", () => {
    const iso = "2026-03-04T12:00:00Z";
    expect(formatDateTime(iso)).toBe(new Date(iso).toLocaleString());
  });

  it("formats a number in the locale's default style", () => {
    expect(formatNumber(1234.5)).toBe((1234.5).toLocaleString());
  });
});
