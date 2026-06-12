import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { FileTreePanel } from "./file-tree-panel";

export interface WE {
  id: string;
  project_id: string;
  parent_id: string | null;
  type: "folder" | "doc" | "file";
  name: string;
  is_root: boolean;
  path: string;
}

export function we(id: string, parent: string | null, type: WE["type"], name: string): WE {
  return { id, project_id: "p", parent_id: parent, type, name, is_root: id === "root", path: name };
}

export function buildTree(entities: WE[]): unknown {
  const build = (n: WE): unknown => ({
    ...n,
    children: entities.filter((e) => e.parent_id === n.id).map(build),
  });
  return build(entities.find((e) => e.is_root)!);
}

export function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function descendants(entities: WE[], id: string): Set<string> {
  const ids = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const e of entities) {
      if (e.parent_id && ids.has(e.parent_id) && !ids.has(e.id)) {
        ids.add(e.id);
        grew = true;
      }
    }
  }
  return ids;
}

export function installFetch(initial: WE[]) {
  let entities = [...initial];
  let counter = 0;
  const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const method = init?.method ?? "GET";
    if (path.endsWith("/tree") && method === "GET") return json({ root: buildTree(entities) }, 200);
    if (path.endsWith("/tree/entities") && method === "POST") {
      const body = JSON.parse(init!.body as string) as {
        type: WE["type"];
        name: string;
        parent_id: string | null;
      };
      const ent = we(`e${++counter}`, body.parent_id ?? "root", body.type, body.name);
      entities.push(ent);
      return json(ent, 201);
    }
    const rn = path.match(/\/tree\/entities\/([^/]+)\/rename$/);
    if (rn && method === "PATCH") {
      const body = JSON.parse(init!.body as string) as { name: string };
      entities = entities.map((e) => (e.id === rn[1] ? { ...e, name: body.name } : e));
      return json(
        entities.find((e) => e.id === rn[1]),
        200,
      );
    }
    const mv = path.match(/\/tree\/entities\/([^/]+)\/move$/);
    if (mv && method === "PATCH") {
      const body = JSON.parse(init!.body as string) as { new_parent_id: string };
      entities = entities.map((e) =>
        e.id === mv[1] ? { ...e, parent_id: body.new_parent_id } : e,
      );
      return json(
        entities.find((e) => e.id === mv[1]),
        200,
      );
    }
    const del = path.match(/\/tree\/entities\/([^/]+)$/);
    if (del && method === "DELETE") {
      const ids = descendants(entities, del[1]);
      entities = entities.filter((e) => !ids.has(e.id));
      return new Response(null, { status: 204 });
    }
    return new Response("nf", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export const BASE: WE[] = [
  we("root", null, "folder", "root"),
  we("chapters", "root", "folder", "Chapters"),
  we("intro", "chapters", "doc", "intro.tex"),
  we("main", "root", "doc", "main.tex"),
];

export function renderPanel(onSelect = vi.fn()) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <FileTreePanel projectId="p" selectedId={null} onSelectEntity={onSelect} />
    </QueryClientProvider>,
  );
  return onSelect;
}

export const row = (name: string) =>
  screen.getByText(name).closest('[role="treeitem"]') as HTMLElement;
export const dragHandle = (name: string) =>
  screen.getByText(name).closest('[draggable="true"]') as HTMLElement;
