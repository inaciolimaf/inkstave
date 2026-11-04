import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { usePersonalDictionary } from "@/modules/spellcheck";

import { DictionarySection } from "./DictionarySection";

vi.mock("@/modules/spellcheck", () => ({ usePersonalDictionary: vi.fn() }));

const remove = vi.fn();

beforeEach(() => {
  remove.mockReset();
});

describe("DictionarySection", () => {
  it("lists the personal words, each with a remove button", async () => {
    vi.mocked(usePersonalDictionary).mockReturnValue({
      words: ["Inkstave", "tectonic"],
      isLoading: false,
      isError: false,
      add: vi.fn(),
      remove,
    });
    render(<DictionarySection />);
    expect(screen.getByText("Inkstave")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Remove tectonic" }));
    expect(remove).toHaveBeenCalledWith("tectonic");
  });

  it("explains an empty dictionary", () => {
    vi.mocked(usePersonalDictionary).mockReturnValue({
      words: [],
      isLoading: false,
      isError: false,
      add: vi.fn(),
      remove,
    });
    render(<DictionarySection />);
    expect(screen.getByText(/No words yet/)).toBeTruthy();
  });
});
