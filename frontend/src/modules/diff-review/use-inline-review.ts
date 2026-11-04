/**
 * Opens a proposal in its document and keeps its review running on the editor's view (spec 110). The review
 * ends when the user closes it, when the document is switched, or when the outcome is recorded. Decisions made
 * so far stay remembered for this page, so reopening the card resumes the undecided hunks.
 */
import type { EditorView } from "@codemirror/view";
import {
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";

import i18n from "@/i18n/config";

import { fetchProposal, recordDecision } from "./api";
import { type ReviewDeps, createReviewActions } from "./inline-review-actions";
import {
  focusHunk,
  inlineReviewField,
  moveReviewHunk,
  startInlineReview,
  stopInlineReview,
} from "./inline-review-extension";
import {
  type Decided,
  type ReviewActions,
  type ReviewSnapshot,
  decisionsOf,
  pendingHunks,
} from "./inline-review-model";
import type { ReviewBarProps } from "./review-bar";
import type { DiffProposal, DocumentBridge } from "./types";

/** A proposal the user asked to review: its session, its id (the diff id) and its document. */
export interface ProposalRef {
  sessionId: string;
  proposalId: string;
  path: string;
}

export interface UseInlineReviewOptions {
  projectId: string;
  bridge: DocumentBridge | undefined;
  /** The editor showing the open document, or null while it mounts. */
  view: EditorView | null;
  openPath: string | null;
  /** Viewers see the changes drawn but cannot decide them. */
  canDecide: boolean;
  /** Opens the document a proposal is about; false when it is not a document of this project. */
  openDocument(path: string): boolean;
  /** The proposal was decided, with its new status. */
  onDecided(proposalId: string, status: string): void;
}

type BarState = Pick<ReviewBarProps, "index" | "total" | "pending" | "readOnly">;

/** The latest options and request, for the callbacks that outlive a render. */
type Latest = UseInlineReviewOptions & { request: ProposalRef | null };

/** Page state a review reads and writes. Refs and setters only, so it never changes between renders. */
interface HookEnv {
  latest: MutableRefObject<Latest>;
  remembered: MutableRefObject<Map<string, Decided>>;
  started: MutableRefObject<EditorView | null>;
  setRequest: Dispatch<SetStateAction<ProposalRef | null>>;
  setBar: Dispatch<SetStateAction<BarState | null>>;
}

const tr = (key: string) => i18n.t(key, { ns: "review" });

/** A write that never answers must not hold a hunk forever (every wait has a deadline). */
const WRITE_DEADLINE_MS = 15_000;

function withDeadline<T>(work: Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("The write did not finish in time.")), WRITE_DEADLINE_MS);
    work.then(resolve, reject).finally(() => clearTimeout(timer));
  });
}

function barOf(review: ReviewSnapshot): BarState {
  return {
    index: review.active + 1,
    total: review.hunks.length,
    pending: pendingHunks(review.hunks).length,
    readOnly: review.readOnly,
  };
}

function reviewEnds(env: HookEnv) {
  env.started.current = null;
  env.setRequest(null);
  env.setBar(null);
}

/** What a review needs from the page, bound to one proposal. */
function depsFor(ref: ProposalRef, env: HookEnv): ReviewDeps {
  const { latest, remembered } = env;
  const bridge = () => latest.current.bridge;
  return {
    view: () => (latest.current.openPath === ref.path ? latest.current.view : null),
    readLive: async (path) => {
      const b = bridge();
      if (!b) throw new Error("No document bridge.");
      return (await withDeadline(b.readContent(path))) ?? "";
    },
    write: (path, target) => {
      const b = bridge();
      if (!b) return Promise.reject(new Error("No document bridge."));
      return withDeadline(b.applyContent(path, target));
    },
    record: (proposalId, lists) => recordDecision(latest.current.projectId, ref.sessionId, proposalId, lists),
    notify: (notice) => toast.error(tr(`toast.${notice}`)),
    finished: (proposalId, status) => {
      remembered.current.delete(proposalId);
      latest.current.onDecided(proposalId, status);
    },
    closed: () => reviewEnds(env),
    changed: (review) => {
      remembered.current.set(review.proposalId, decisionsOf(review.hunks));
      env.setBar(barOf(review));
    },
  };
}

/** Starts the review of a fetched proposal on the view, with the decisions remembered for it. */
function startOn(view: EditorView, ref: ProposalRef, env: HookEnv, proposal: DiffProposal) {
  const actions: ReviewActions = createReviewActions(depsFor(ref, env));
  view.dispatch({
    effects: startInlineReview.of({
      proposalId: proposal.id,
      path: ref.path,
      readOnly: !env.latest.current.canDecide,
      hunks: proposal.files[0]?.hunks ?? [],
      decided: env.remembered.current.get(proposal.id) ?? {},
      actions,
    }),
  });
  const review = view.state.field(inlineReviewField);
  if (review) focusHunk(view, review.active);
  actions.settle();
}

/** Loads the proposal and starts its review, unless the page has moved on since. */
function loadAndStart(view: EditorView, ref: ProposalRef, env: HookEnv) {
  const { latest, started } = env;
  started.current = view;
  void fetchProposal(latest.current.projectId, ref.sessionId, ref.proposalId).then(
    (proposal) => {
      const now = latest.current;
      if (now.view !== view || now.request?.proposalId !== ref.proposalId) return;
      if (!proposal || proposal.status !== "proposed") {
        if (proposal) now.onDecided(proposal.id, proposal.status);
        toast.message(tr("toast.alreadyDecided"));
        reviewEnds(env);
        return;
      }
      startOn(view, ref, env, proposal);
    },
    () => {
      started.current = null;
      toast.error(tr("toast.loadError"));
    },
  );
}

export function useInlineReview(options: UseInlineReviewOptions) {
  const { view, openPath, projectId, canDecide } = options;
  const [request, setRequest] = useState<ProposalRef | null>(null);
  const [bar, setBar] = useState<BarState | null>(null);
  const remembered = useRef(new Map<string, Decided>());
  const started = useRef<EditorView | null>(null);
  // The editor that was showing another document when a review asked for a switch. The open path changes at once,
  // but the proposal's editor mounts a moment later: starting on this one would end the review when it unmounts,
  // so the user had to click twice.
  const leaving = useRef<EditorView | null>(null);
  const latest = useRef<Latest>({ ...options, request });
  latest.current = { ...options, request };
  const env = useMemo<HookEnv>(() => ({ latest, remembered, started, setRequest, setBar }), []);

  // A review belongs to the view it started on: when that view goes (another document opens), it ends.
  useEffect(() => {
    if (started.current && started.current !== view) reviewEnds(env);
  }, [view, env]);

  // Start the review once the open document is the proposal's and its editor is mounted.
  useEffect(() => {
    if (!request || !view || openPath !== request.path || started.current === view) return;
    if (view === leaving.current) return;
    leaving.current = null;
    loadAndStart(view, request, env);
  }, [request, view, openPath, projectId, canDecide, env]);

  /** Opens the review of a proposal, switching the editor to its document first. */
  const open = useCallback((ref: ProposalRef) => {
    const page = latest.current;
    leaving.current = page.openPath === ref.path ? null : page.view;
    if (!page.openDocument(ref.path)) {
      toast.message(tr("toast.notInProject"));
      return;
    }
    if (started.current) {
      started.current.dispatch({ effects: stopInlineReview.of(null) });
      started.current = null;
    }
    setBar(null);
    setRequest(ref);
  }, []);

  const actionsNow = () => latest.current.view?.state.field(inlineReviewField)?.actions ?? null;
  const bindings = {
    onPrevious: () => {
      const v = latest.current.view;
      if (v) moveReviewHunk(v, -1);
    },
    onNext: () => {
      const v = latest.current.view;
      if (v) moveReviewHunk(v, 1);
    },
    onAcceptAll: () => actionsNow()?.acceptAll(),
    onRejectAll: () => actionsNow()?.rejectAll(),
    onClose: () => {
      const actions = actionsNow();
      if (actions) actions.close();
      else reviewEnds(env);
    },
  };

  return { open, bar: bar ? { ...bar, ...bindings } : null };
}
