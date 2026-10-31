/** A piece of the document handed to the agent, and how the editor asks the agent for something. */
export interface AgentQuote {
  path: string;
  /** 1-based, inclusive. */
  fromLine: number;
  toLine: number;
  text: string;
}

export interface AgentRequest {
  /** Attach this selection to the next message. */
  quote?: AgentQuote;
  /** Send this message straight away. */
  send?: string;
}

/** The agent has no notion of a selection: the quoted text travels in the message itself. */
export function withQuote(text: string, quote: AgentQuote | null): string {
  if (!quote) return text;
  const where = `${quote.path}, lines ${quote.fromLine}-${quote.toLine}`;
  const fence = "```";
  return `${text}\n\nSelected text from ${where}:\n${fence}\n${quote.text}\n${fence}`;
}
