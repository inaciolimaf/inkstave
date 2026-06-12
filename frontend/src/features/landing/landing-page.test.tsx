import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "@/auth/auth-context";

import { LandingPage } from "./landing-page";

function renderLanding() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AuthProvider>
        <LandingPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LandingPage", () => {
  it("renders the hero with the primary call to action", async () => {
    renderLanding();

    // Serif headline is split across nodes; assert on its parts.
    expect(await screen.findByText(/Write LaTeX/)).toBeInTheDocument();
    expect(screen.getByText("literature.")).toBeInTheDocument();

    // Primary CTA sends unauthenticated visitors to sign in.
    const start = screen.getByRole("link", { name: "Start writing" });
    expect(start).toHaveAttribute("href", "/login");
  });

  it("shows the signed-out nav actions", async () => {
    renderLanding();

    const banner = await screen.findByRole("banner");
    expect(within(banner).getByRole("link", { name: /get started/i })).toHaveAttribute(
      "href",
      "/register",
    );
    expect(within(banner).getByRole("link", { name: /sign in/i })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("expands an FAQ entry when its question is clicked", async () => {
    const user = userEvent.setup();
    renderLanding();

    const question = await screen.findByRole("button", {
      name: /which latex engine compiles my work/i,
    });
    expect(question).toHaveAttribute("aria-expanded", "false");

    await user.click(question);
    expect(question).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Tectonic, a modern and reproducible TeX engine/i)).toBeInTheDocument();
  });
});
