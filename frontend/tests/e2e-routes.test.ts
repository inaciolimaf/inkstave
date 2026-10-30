import { describe, expect, it } from "vitest";

import { ROUTE_PATHS } from "@/router";

import { ROUTES } from "../e2e/support/routes";

describe("the e2e route list", () => {
  it("covers every route of the router, and nothing else", () => {
    expect(ROUTES.map((route) => route.path).sort()).toEqual([...ROUTE_PATHS].sort());
  });
});
