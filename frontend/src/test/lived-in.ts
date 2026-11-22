/**
 * A "lived-in" project for component tests: the data a real project already carries (content,
 * recorded history, a comment thread, a pending agent proposal, a share link, a collaborator).
 *
 * It mirrors `backend/tests/factories/lived_in.py` in shape and text. The API answers come from
 * `installLivedInFetch()`, which stubs `fetch` with the snake_case wire JSON the real endpoints send,
 * so the panels exercise their real API modules.
 */
import { vi } from "vitest";

export const LIVED = {
  projectId: "p-lived",
  sessionId: "s-lived",
  proposalId: "d-lived",
  threadId: "t-lived",
  ids: {
    root: "root",
    chapters: "chapters",
    figures: "figures",
    main: "main",
    intro: "intro",
    methods: "methods",
    refs: "refs",
    plot: "plot",
    appendix: "appendix",
  },
  owner: { id: "u-owner", name: "Ada Lovelace", email: "ada@example.com" },
  collaborator: { id: "u-editor", name: "Grace Hopper", email: "grace@example.com" },
  /** Document text, keyed by tree path. */
  contents: {
    "main.tex": "\\documentclass{article}\n\\input{chapters/intro}\n\\input{chapters/methods}\n",
    "chapters/intro.tex":
      "\\section{Introduction}\nLévy flights in café-style prose, seeded before any edit.\n",
    "chapters/methods.tex": "\\section{Methods}\nWe follow \\cite{knuth84} closely.\n",
    "refs.bib": "@book{knuth84,\n  title={The TeXbook}\n}\n",
    "appendix.tex": "\\appendix\n\\section{Legacy notes}\nWritten before history existed.\n",
  } as Record<string, string>,
  /** Recorded versions of main.tex; appendix.tex has none. */
  mainVersions: [1, 2],
} as const;

const TS = "2026-11-20T12:00:00.000Z";

interface Node {
  id: string;
  project_id: string;
  parent_id: string | null;
  type: "folder" | "doc" | "file";
  name: string;
  is_root: boolean;
  created_at: string;
  updated_at: string;
  path: string;
  children: Node[] | null;
}

function node(
  id: string,
  parent: string | null,
  type: Node["type"],
  name: string,
  path: string,
  is_root = false,
): Node {
  return {
    id,
    project_id: LIVED.projectId,
    parent_id: parent,
    type,
    name,
    is_root,
    created_at: TS,
    updated_at: TS,
    path,
    children: type === "folder" ? [] : null,
  };
}

/** The nested tree as `GET /tree` returns it: root, then folders with children, docs and files as leaves. */
export function livedInTree(): { root: Node } {
  const { ids } = LIVED;
  const intro = node(ids.intro, ids.chapters, "doc", "intro.tex", "chapters/intro.tex");
  const methods = node(ids.methods, ids.chapters, "doc", "methods.tex", "chapters/methods.tex");
  const chapters = {
    ...node(ids.chapters, ids.root, "folder", "chapters", "chapters"),
    children: [intro, methods],
  };
  const plot = node(ids.plot, ids.figures, "file", "plot.png", "figures/plot.png");
  const figures = { ...node(ids.figures, ids.root, "folder", "figures", "figures"), children: [plot] };
  const root = {
    ...node(ids.root, null, "folder", "", "", true),
    children: [
      chapters,
      figures,
      node(ids.main, ids.root, "doc", "main.tex", "main.tex"),
      node(ids.refs, ids.root, "doc", "refs.bib", "refs.bib"),
      node(ids.appendix, ids.root, "doc", "appendix.tex", "appendix.tex"),
    ],
  };
  return { root };
}

/** The document-read payload (`GET /documents/{id}`) for a path. */
export function livedInDocument(path: string) {
  return { entity_id: pathToId(path), content: LIVED.contents[path], version: path === "main.tex" ? 2 : 1 };
}

const DOC_IDS: Record<string, string> = {
  "main.tex": LIVED.ids.main,
  "chapters/intro.tex": LIVED.ids.intro,
  "chapters/methods.tex": LIVED.ids.methods,
  "refs.bib": LIVED.ids.refs,
  "appendix.tex": LIVED.ids.appendix,
};

function pathToId(path: string): string {
  return DOC_IDS[path] ?? "";
}

const author = { id: LIVED.owner.id, name: LIVED.owner.name, email: LIVED.owner.email };

/** The version list of main.tex, in the wire shape of `GET .../history/versions`. */
export function livedInVersions(docId: string) {
  const versions = docId === LIVED.ids.main ? LIVED.mainVersions : [];
  return {
    doc_id: docId,
    current_version: versions.length,
    versions: versions.map((version) => ({
      version,
      timestamp: TS,
      author,
      op_count: 1,
      size: LIVED.contents["main.tex"].length,
      labels: [],
      origin: null,
    })),
    has_more: false,
    next_before: null,
  };
}

/** One comment thread on intro.tex, in the wire shape of `GET .../comments`. */
export function livedInComments() {
  const message = {
    id: "m-comment",
    author: { id: LIVED.collaborator.id, name: LIVED.collaborator.name, email: LIVED.collaborator.email },
    body: "Is 'seeded' the right word here?",
    mentions: [],
    created_at: TS,
    edited_at: null,
    deleted_at: null,
  };
  return {
    items: [
      {
        id: LIVED.threadId,
        document_id: LIVED.ids.intro,
        anchor_start: "AQ==",
        anchor_end: "Ag==",
        quoted_text: "seeded",
        author: message.author,
        created_at: TS,
        resolved_at: null,
        resolved_by: null,
        messages: [message],
      },
    ],
    has_more: false,
    next_cursor: null,
  };
}

const session = {
  id: LIVED.sessionId,
  project_id: LIVED.projectId,
  title: "Polish",
  status: "active",
  run_state: "idle",
  model: "fake/model",
  created_at: TS,
  updated_at: TS,
};

const messages = [
  {
    id: "m-ask",
    seq: 1,
    role: "user",
    content: "Tighten the introduction.",
    tool_call_id: null,
    tool_calls: null,
  },
  {
    id: "m-reply",
    seq: 2,
    role: "assistant",
    content: "Here is a tighter version.",
    tool_call_id: null,
    tool_calls: null,
  },
];

const proposal = {
  id: LIVED.proposalId,
  message_id: "m-reply",
  doc_id: LIVED.ids.intro,
  path: "chapters/intro.tex",
  base_version: "1",
  status: "proposed",
  stats: { additions: 1, deletions: 1, hunk_count: 1 },
  rationale: "Make the introduction less tentative.",
  created_at: TS,
};

/** The session list and the session detail with its transcript and proposal. */
export function livedInSessions() {
  return [session];
}

export function livedInSessionDetail() {
  return { session, messages, diffs: [proposal], file_ops: [] };
}

/** `GET .../history/diff` between version 1 and the current text of main.tex. */
function livedInDiff() {
  return {
    from: 1,
    to: "current",
    binary: false,
    too_large: false,
    hunks: [
      {
        old_start: 1,
        old_lines: 1,
        new_start: 1,
        new_lines: 2,
        segments: [
          { type: "context", value: "\\documentclass{article}\n" },
          { type: "added", value: "\\input{chapters/intro}\n" },
        ],
      },
    ],
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/**
 * Stub `fetch` with the lived-in project. Unknown routes answer 404, so a test that reaches for
 * data the project does not have fails loudly.
 */
export function installLivedInFetch(options: { capabilities?: string[] } = {}) {
  const capabilities = options.capabilities ?? ["doc_read", "doc_write", "comment", "history_restore"];
  const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const method = init?.method ?? "GET";
    if (method !== "GET") return json({ detail: "read-only fixture" }, 405);
    if (path.endsWith("/tree")) return json({ root: livedInTree().root });
    if (path.endsWith("/permissions")) return json({ role: "owner", capabilities });
    const versions = path.match(/\/docs\/([^/]+)\/history\/versions$/);
    if (versions) return json(livedInVersions(versions[1]));
    if (path.endsWith("/history/diff")) return json(livedInDiff());
    if (path.endsWith("/history/labels")) return json([]);
    if (path.endsWith("/comments")) return json(livedInComments());
    if (path.endsWith("/agent/sessions")) return json(livedInSessions());
    if (path.endsWith(`/agent/sessions/${LIVED.sessionId}`)) return json(livedInSessionDetail());
    if (path.endsWith(`/agent/sessions/${LIVED.sessionId}/diffs`)) return json([proposal]);
    const doc = path.match(/\/documents\/([^/]+)$/);
    const docPath = doc ? Object.keys(LIVED.contents).find((p) => pathToId(p) === doc[1]) : undefined;
    if (docPath) return json(livedInDocument(docPath));
    return json({ detail: "not found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
