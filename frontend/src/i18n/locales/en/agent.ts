/** Strings for the AI agent chat panel (the `agent` namespace, spec 46). */
const dict = {
  ariaLabel: "AI agent",
  newChat: "New chat",
  sessions: "Sessions",
  untitledChat: "Untitled chat",
  description: "Chat with the AI writing assistant. It proposes changes for you to review.",
  resizeHandle: "Resize agent panel",
  loadingConversation: "Loading conversation",
  empty: {
    intro:
      "Ask the agent to read or revise your project. It proposes changes you review — it never edits files directly.",
    example1: "Rewrite the introduction to be more concise.",
    example2: "Find where the methodology section is defined.",
    example3: "Add a conclusion summarising the key results.",
  },
  composer: {
    placeholder: "Ask the agent to read or edit the project…",
    messageLabel: "Message the agent",
    sendLabel: "Send message",
    sendTooltip: "Send (Enter)",
  },
  run: {
    stop: "Stop",
    stopLabel: "Stop the run",
  },
  error: {
    retry: "Retry",
    generic: "Error",
    titles: {
      transport: "Connection lost",
      internal: "Run failed",
      llm_error: "AI service unavailable",
      rate_limited: "Rate limit reached",
      agent_rate_limited: "Rate limit reached",
      budget_exceeded: "Budget exceeded",
      agent_budget_exceeded: "Budget reached",
      cancelled: "Run cancelled",
      timeout: "Run timed out",
    },
    messages: {
      cancelled: "Run cancelled.",
      agent_rate_limited: "You’ve hit the agent rate limit. Please try again shortly.",
      rate_limited: "You’ve hit a usage limit. Please try again shortly.",
      agent_budget_exceeded: "This run reached the token or cost budget.",
      budget_exceeded: "This run would exceed the token budget.",
      llm_error: "The AI service is temporarily unavailable.",
      internal: "The agent run failed. Please try again.",
      timeout: "The run took too long and was stopped. Try a smaller task — e.g. one file or section at a time.",
      generic: "Something went wrong.",
      connectionLost: "Connection lost.",
      startFailed: "Failed to start the run.",
    },
  },
  transcript: {
    conversation: "Conversation",
    jumpToLatest: "Jump to latest",
    runCancelled: "Run cancelled",
    tools: {
      search_project: "Searched the project",
      read_file: "Read a file",
      list_tree: "Listed the file tree",
      locate_section: "Located a section",
      propose_edit: "Proposed an edit",
    },
    proposedChanges: "Proposed changes",
    hunkLine_one: "{{path}} · {{count}} hunk",
    hunkLine_other: "{{path}} · {{count}} hunks",
    reviewChanges: "Review changes",
    reviewChangesCount: "Review changes ({{count}})",
  },
};

export default dict;
export type Dict = typeof dict;
