import { describe, expect, it } from "vitest";

import type { Project } from "./types";
import { visibleProjects } from "./use-projects";

function p(over: Partial<Project>): Project {
  return {
    id: "id",
    name: "Name",
    ownerId: "u",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    ...over,
  };
}

const projects = [
  p({ id: "1", name: "Beta", createdAt: "2026-01-01", updatedAt: "2026-01-02" }),
  p({ id: "2", name: "alpha", createdAt: "2026-01-03", updatedAt: "2026-01-05" }),
  p({ id: "3", name: "Gamma", createdAt: "2026-01-02", updatedAt: "2026-01-03" }),
];

describe("visibleProjects", () => {
  it("filters by name case-insensitively", () => {
    const result = visibleProjects(projects, "AL", "name");
    expect(result.map((x) => x.id)).toEqual(["2"]);
  });

  it("returns everything when the search is blank", () => {
    expect(visibleProjects(projects, "  ", "name")).toHaveLength(3);
  });

  it("sorts by name A–Z (case-insensitive locale order)", () => {
    expect(visibleProjects(projects, "", "name").map((x) => x.name)).toEqual([
      "alpha",
      "Beta",
      "Gamma",
    ]);
  });

  it("sorts by last modified (newest first)", () => {
    expect(visibleProjects(projects, "", "updatedAt").map((x) => x.id)).toEqual(["2", "3", "1"]);
  });

  it("sorts by created (newest first)", () => {
    expect(visibleProjects(projects, "", "createdAt").map((x) => x.id)).toEqual(["2", "3", "1"]);
  });

  it("does not mutate the input array", () => {
    const copy = [...projects];
    visibleProjects(projects, "", "name");
    expect(projects).toEqual(copy);
  });
});
