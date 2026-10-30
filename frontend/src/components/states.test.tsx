import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { QueryView } from "./states";

const query = { data: undefined, isLoading: false, isError: false, refetch: vi.fn() };

describe("QueryView", () => {
  it("shows the loading state while the query loads", () => {
    render(
      <QueryView query={{ ...query, isLoading: true }} loading={<p>Wait</p>}>
        {() => <p>Data</p>}
      </QueryView>,
    );
    expect(screen.getByText("Wait")).toBeInTheDocument();
  });

  it("shows the error with a working retry", async () => {
    const refetch = vi.fn();
    render(
      <QueryView query={{ ...query, isError: true, refetch }} errorMessage="It failed">
        {() => <p>Data</p>}
      </QueryView>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("It failed");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("treats a settled query without data as an error", () => {
    render(<QueryView query={query}>{() => <p>Data</p>}</QueryView>);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong. Please try again.");
  });

  it("renders the data", () => {
    render(<QueryView query={{ ...query, data: "hello" }}>{(data) => <p>{data}</p>}</QueryView>);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });
});
