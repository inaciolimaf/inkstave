/**
 * A tiny backend API client for the e2e suite (spec 54).
 *
 * Used by global setup (register users) and by specs to *fast-seed* state via
 * the API — a project with files — for journeys that aren't about that setup, so
 * specs stay short and fast (spec 54 §5.1). It talks to the real backend exactly
 * as the browser would; only the auth journey drives register/login through the UI.
 */
import { e2e, E2E_PASSWORD } from "./env";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export class ApiClient {
  constructor(
    private readonly base = e2e.apiUrl,
    public accessToken: string | null = null,
  ) {}

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "content-type": "application/json" };
    if (this.accessToken) headers.authorization = `Bearer ${this.accessToken}`;
    const res = await fetch(`${this.base}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${method} ${path} -> ${res.status}: ${text}`);
    }
    if (res.status === 204) return undefined as T;
    const ct = res.headers.get("content-type") ?? "";
    return (ct.includes("application/json") ? await res.json() : await res.text()) as T;
  }

  async register(
    email: string,
    displayName: string,
    password = E2E_PASSWORD,
  ): Promise<{ id: string }> {
    return this.request("POST", "/api/v1/auth/register", {
      email,
      display_name: displayName,
      password,
    });
  }

  /**
   * Create the first admin via the first-run setup gate, taking the app past
   * setup so `needs_setup` is false (unauthenticated users redirect to /login,
   * not /setup). Idempotent for e2e: a 409 means an admin already exists.
   */
  async bootstrapAdmin(email: string, displayName: string, password = E2E_PASSWORD): Promise<void> {
    const res = await fetch(`${this.base}/api/setup/admin`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, display_name: displayName, password }),
    });
    if (!res.ok && res.status !== 409) {
      throw new Error(`POST /api/setup/admin -> ${res.status}: ${await res.text()}`);
    }
  }

  async login(email: string, password = E2E_PASSWORD): Promise<TokenPair> {
    const pair = await this.request<TokenPair>("POST", "/api/v1/auth/login", { email, password });
    this.accessToken = pair.access_token;
    return pair;
  }

  async createProject(name: string): Promise<{ id: string }> {
    return this.request("POST", "/api/v1/projects", { name });
  }

  async getTree(projectId: string): Promise<{ root: TreeNode }> {
    return this.request("GET", `/api/v1/projects/${projectId}/tree`);
  }

  /** Return the first document entity in the project's tree, if any. */
  async firstDoc(projectId: string): Promise<TreeNode | null> {
    const { root } = await this.getTree(projectId);
    const find = (n: TreeNode): TreeNode | null => {
      if (n.type === "doc") return n;
      for (const c of n.children ?? []) {
        const hit = find(c);
        if (hit) return hit;
      }
      return null;
    };
    return find(root);
  }

  async createDoc(
    projectId: string,
    name: string,
    parentId: string | null = null,
  ): Promise<TreeNode> {
    return this.request("POST", `/api/v1/projects/${projectId}/tree/entities`, {
      type: "doc",
      name,
      parent_id: parentId,
    });
  }

  async getDoc(projectId: string, docId: string): Promise<{ version: number; content: string }> {
    return this.request("GET", `/api/v1/projects/${projectId}/documents/${docId}`);
  }

  async putDoc(
    projectId: string,
    docId: string,
    content: string,
    baseVersion: number,
  ): Promise<{ version: number }> {
    return this.request("PUT", `/api/v1/projects/${projectId}/documents/${docId}`, {
      content,
      base_version: baseVersion,
    });
  }

  /** Set a document's content regardless of its current version. */
  async setDocContent(projectId: string, docId: string, content: string): Promise<void> {
    const { version } = await this.getDoc(projectId, docId);
    await this.putDoc(projectId, docId, content, version);
  }

  async listVersions(
    projectId: string,
    docId: string,
  ): Promise<{ versions: { version: number }[]; current_version: number }> {
    return this.request("GET", `/api/v1/projects/${projectId}/docs/${docId}/history/versions`);
  }

  /** Poll the history API until at least `min` versions exist (capture is async). */
  async waitForVersions(
    projectId: string,
    docId: string,
    min: number,
    timeoutMs = 15_000,
  ): Promise<number> {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const { versions } = await this.listVersions(projectId, docId);
      if (versions.length >= min) return versions.length;
      if (Date.now() > deadline) {
        throw new Error(
          `only ${versions.length} history versions after ${timeoutMs}ms (wanted ${min})`,
        );
      }
      await new Promise((r) => setTimeout(r, 200));
    }
  }

  // --- compile + agent (used by the harness sanity spec) ------------------- //

  async requestCompile(projectId: string): Promise<CompileStatus> {
    return this.request("POST", `/api/v1/projects/${projectId}/compile`, {
      main_file: null,
      force: true,
    });
  }

  async waitForCompile(projectId: string, timeoutMs = 20_000): Promise<CompileStatus> {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const latest = await this.request<CompileStatus>(
        "GET",
        `/api/v1/projects/${projectId}/compile/latest`,
      );
      if (["success", "failure", "error", "timeout"].includes(latest.status)) return latest;
      if (Date.now() > deadline) throw new Error(`compile not terminal after ${timeoutMs}ms`);
      await new Promise((r) => setTimeout(r, 200));
    }
  }

  async getCompilePdfBytes(projectId: string, compileId: string): Promise<Uint8Array> {
    const headers: Record<string, string> = {};
    if (this.accessToken) headers.authorization = `Bearer ${this.accessToken}`;
    const res = await fetch(
      `${this.base}/api/v1/projects/${projectId}/compile/${compileId}/output.pdf`,
      { headers },
    );
    if (!res.ok) throw new Error(`pdf fetch -> ${res.status}`);
    return new Uint8Array(await res.arrayBuffer());
  }

  async getCompileLog(projectId: string, compileId: string): Promise<string> {
    return this.request("GET", `/api/v1/projects/${projectId}/compile/${compileId}/output.log`);
  }

  async createAgentSession(projectId: string): Promise<{ id: string }> {
    return this.request("POST", `/api/v1/projects/${projectId}/agent/sessions`, { title: null });
  }

  async postAgentMessage(
    projectId: string,
    sessionId: string,
    content: string,
  ): Promise<{ run_id: string }> {
    return this.request(
      "POST",
      `/api/v1/projects/${projectId}/agent/sessions/${sessionId}/messages`,
      {
        content,
      },
    );
  }

  async waitForAgentDiff(
    projectId: string,
    sessionId: string,
    timeoutMs = 20_000,
  ): Promise<AgentDiff[]> {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const diffs = await this.request<AgentDiff[]>(
        "GET",
        `/api/v1/projects/${projectId}/agent/sessions/${sessionId}/diffs?include=hunks`,
      );
      if (diffs.length > 0) return diffs;
      if (Date.now() > deadline) throw new Error(`no agent diff after ${timeoutMs}ms`);
      await new Promise((r) => setTimeout(r, 200));
    }
  }

  async invite(
    projectId: string,
    email: string,
    role: "editor" | "viewer",
  ): Promise<{ token: string }> {
    return this.request("POST", `/api/v1/projects/${projectId}/invites`, { email, role });
  }

  async acceptInvite(token: string): Promise<{ projectId?: string; project_id?: string }> {
    return this.request("POST", `/api/v1/invites/${token}/accept`, {});
  }
}

export interface TreeNode {
  id: string;
  type: "folder" | "doc" | "file";
  name: string;
  path: string;
  children?: TreeNode[] | null;
}

export interface CompileStatus {
  id: string;
  status: "queued" | "running" | "success" | "failure" | "error" | "timeout";
  has_pdf: boolean;
}

export interface AgentDiff {
  id: string;
  path: string;
  status: string;
  hunks?: unknown[];
}

/** Register a user and return an authenticated client plus a refresh token. */
export async function registerUser(
  email: string,
  displayName: string,
): Promise<{ client: ApiClient; id: string; refreshToken: string }> {
  const client = new ApiClient();
  const { id } = await client.register(email, displayName);
  const pair = await client.login(email);
  return { client, id, refreshToken: pair.refresh_token };
}

/** A run-unique suffix so parallel workers and reruns never collide on emails/names. */
export function uniqueId(prefix: string): string {
  // Deterministic-enough uniqueness without Date.now(): worker id + a counter.
  const worker = process.env.TEST_PARALLEL_INDEX ?? process.env.TEST_WORKER_INDEX ?? "0";
  uniqueId.counter += 1;
  return `${prefix}-w${worker}-${uniqueId.counter}-${process.pid}`;
}
uniqueId.counter = 0;
