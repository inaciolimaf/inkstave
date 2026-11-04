/**
 * The comment threads in the editor (spec 118): the editor-bar button, the "Comment" button on a selection,
 * the highlights in the text, the deep link from the bell, and the panel. Comments need the collaborative
 * editor, whose Y.Text the view exposes; without it the button and the selection offer stay hidden.
 */
import { StateEffect } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ySyncFacet } from "y-codemirror.next";
import type * as Y from "yjs";

import { useMediaQuery } from "@/lib/use-media-query";
import { useAuth } from "@/modules/auth";
import {
  type CommentMarkHandlers,
  type CommentThread,
  CommentsButton,
  CommentsPanel,
  commentMarks,
  encodeAnchor,
  quoteOf,
  resolveAnchor,
  setCommentMarks,
  useCommentMutations,
  useCommentThreads,
} from "@/modules/discussion";
import { type TreeNode, findNode, useProjectTree } from "@/modules/file-tree";
import { type Member, listMembers } from "@/modules/sharing";

import { CommentSelectionButton } from "./comment-selection-button";
import { useEditorSelection } from "./use-editor-selection";
import { useSuggestionReview } from "./use-suggestion-review";

const NO_THREADS: CommentThread[] = [];

interface Draft {
  documentId: string;
  anchorStart: string;
  anchorEnd: string;
  quote: string;
}

/** The Y.Text behind a view, when the editor is collaborative. */
function yTextOf(view: EditorView | null): Y.Text | null {
  if (!view) return null;
  const sync = view.state.facet(ySyncFacet) as { ytext?: Y.Text } | undefined;
  return sync?.ytext ?? null;
}

function namesById(root: TreeNode | undefined): Map<string, string> {
  const names = new Map<string, string>();
  const visit = (node: TreeNode) => {
    names.set(node.id, node.name);
    node.children.forEach(visit);
  };
  if (root) visit(root);
  return names;
}

/** Puts the cursor where the thread's text is now. A selection would bring up the Comment button again. */
function revealThread(view: EditorView | null, text: Y.Text | null, thread: CommentThread): void {
  if (!view || !text) return;
  const range = resolveAnchor(text, thread.anchor_start, thread.anchor_end);
  if (range) {
    view.dispatch({
      selection: { anchor: range.from },
      effects: EditorView.scrollIntoView(range.from, { y: "center" }),
    });
  }
}

/** The project's members as mention candidates, without the viewer. Fetched while the panel is open. */
function useMentionMembers(projectId: string, meId: string | null, enabled: boolean) {
  const query = useQuery({
    queryKey: ["members", projectId],
    queryFn: () => listMembers(projectId),
    enabled,
  });
  return (query.data ?? [])
    .filter((m: Member) => m.userId !== meId)
    .map((m) => ({ id: m.userId, name: m.name }));
}

/** The state of the comments: the threads, the panel, the draft on a selection and the selected thread. */
function useCommentState(
  projectId: string,
  view: EditorView | null,
  openEntity: { id: string; type: string } | null,
  onOpenDocument: (node: TreeNode) => void,
) {
  const treeRoot = useProjectTree(projectId).data;
  const threads = useCommentThreads(projectId);
  const text = useMemo(() => yTextOf(view), [view]);
  const documentId = openEntity?.type === "doc" ? openEntity.id : null;
  const list = useMemo(() => threads.data ?? NO_THREADS, [threads.data]);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selectThread = (thread: CommentThread) => {
    setSelectedId(thread.id);
    if (thread.document_id !== documentId) {
      const node = treeRoot ? findNode(treeRoot, thread.document_id) : null;
      if (node) onOpenDocument(node);
      return;
    }
    revealThread(view, text, thread);
  };

  const startDraft = (): boolean => {
    if (!view || !text || !documentId) return false;
    const { from, to } = view.state.selection.main;
    if (from === to) return false;
    const anchors = encodeAnchor(text, from, to);
    setDraft({ documentId, ...anchors, quote: quoteOf(view.state.sliceDoc(from, to)) });
    setOpen(true);
    return true;
  };

  return {
    treeRoot,
    threads,
    text,
    documentId,
    list,
    open,
    setOpen,
    draft,
    setDraft,
    selectedId,
    setSelectedId,
    selectThread,
    startDraft,
  };
}

/** The effects that keep the editor in step with the threads: the highlights, the deep link. */
function useCommentEffects(
  state: ReturnType<typeof useCommentState>,
  view: EditorView | null,
  handlers: { current: CommentMarkHandlers },
) {
  const { text, list, documentId, selectedId, selectThread, setOpen } = state;
  // Installed once per view. This effect comes before the marks effect, so the marks land in the view.
  const installed = useRef(new WeakSet<EditorView>());
  useEffect(() => {
    if (!view || !text || installed.current.has(view)) return;
    installed.current.add(view);
    view.dispatch({ effects: StateEffect.appendConfig.of(commentMarks(text, handlers)) });
  }, [view, text, handlers]);

  useEffect(() => {
    if (!view || !text) return;
    const marks = list
      .filter((t) => t.document_id === documentId && t.resolved_at === null)
      .map((t) => ({ id: t.id, anchorStart: t.anchor_start, anchorEnd: t.anchor_end }));
    view.dispatch({ effects: setCommentMarks.of({ marks, selectedId }) });
  }, [view, text, list, documentId, selectedId]);

  // The deep link from the bell: /projects/:id?thread=... opens the panel on that thread, once.
  const [params, setParams] = useSearchParams();
  const deepLink = params.get("thread");
  useEffect(() => {
    const thread = deepLink ? list.find((t) => t.id === deepLink) : undefined;
    if (!thread) return;
    setOpen(true);
    selectThread(thread);
    setParams(
      (previous) => {
        previous.delete("thread");
        return previous;
      },
      { replace: true },
    );
    // selectThread reads the open document and the tree as of this render; the link is consumed once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLink, list]);
}

/**
 * Everything the editor shows for comments. `chatButton` is the chat's own bar button, which this returns
 * next to the comments button, so the bar takes one slot.
 */
export function useWorkspaceComments(
  projectId: string,
  view: EditorView | null,
  openEntity: { id: string; type: string } | null,
  onOpenDocument: (node: TreeNode) => void,
  chatButton: ReactNode,
) {
  const { user } = useAuth();
  const wide = useMediaQuery("(min-width: 768px)");
  const state = useCommentState(projectId, view, openEntity, onOpenDocument);
  const { selection } = useEditorSelection(state.text ? view : null);
  const { create } = useCommentMutations(projectId);
  const members = useMentionMembers(projectId, user?.id ?? null, state.open);
  const names = useMemo(() => namesById(state.treeRoot), [state.treeRoot]);

  const handlers = useRef<CommentMarkHandlers>({ onSelect: () => {}, onNew: () => false });
  handlers.current = {
    onSelect: (threadId) => {
      const thread = state.list.find((t) => t.id === threadId);
      if (thread) state.selectThread(thread);
    },
    onNew: () => state.startDraft(),
  };
  useCommentEffects(state, view, handlers);

  const { draft, setDraft, setSelectedId, setOpen, text } = state;
  const suggestions = useSuggestionReview(projectId, text);
  const openCount = state.list.filter((t) => t.resolved_at === null).length;
  const hasComments = text !== null;
  const button = hasComments ? (
    <>
      {chatButton}
      <CommentsButton openCount={openCount} onOpen={() => setOpen(true)} />
    </>
  ) : (
    chatButton
  );
  const selectionButton =
    hasComments && state.documentId && selection ? (
      <CommentSelectionButton selection={selection} floating={wide} onComment={() => state.startDraft()} />
    ) : null;

  const panel = hasComments ? (
    <CommentsPanel
      open={state.open}
      onOpenChange={setOpen}
      wide={wide}
      projectId={projectId}
      threads={state.list}
      ytext={text}
      currentDocumentId={state.documentId}
      fileName={(id) => names.get(id) ?? ""}
      members={members}
      meId={user?.id ?? null}
      selectedId={state.selectedId}
      onSelect={state.selectThread}
      draft={draft ? { quote: draft.quote } : null}
      creating={create.isPending}
      onCreate={(body, mentions) => {
        if (!draft) return;
        create.mutate(
          {
            documentId: draft.documentId,
            anchorStart: draft.anchorStart,
            anchorEnd: draft.anchorEnd,
            quotedText: draft.quote,
            body,
            mentions,
          },
          {
            onSuccess: (thread) => {
              setDraft(null);
              setSelectedId(thread.id);
            },
          },
        );
      }}
      onDraftCancel={() => setDraft(null)}
      suggestions={suggestions}
    />
  ) : null;

  return { button, selectionButton, panel };
}

export type WorkspaceComments = ReturnType<typeof useWorkspaceComments>;
