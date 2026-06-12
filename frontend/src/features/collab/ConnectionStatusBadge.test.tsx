import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConnectionStatusBadge } from "./ConnectionStatusBadge";
import type { CollabStatus } from "./useCollabDoc";

describe("ConnectionStatusBadge", () => {
  it.each([
    ["connected", "Live"],
    ["connecting", "Connecting…"],
    ["reconnecting", "Reconnecting…"],
    ["offline", "Offline"],
  ] as [CollabStatus, string][])("renders %s as '%s'", (status, label) => {
    render(<ConnectionStatusBadge status={status} />);
    const badge = screen.getByLabelText(`Connection: ${label}`);
    expect(badge).toHaveTextContent(label);
    expect(badge).toHaveAttribute("aria-live", "polite");
  });
});
