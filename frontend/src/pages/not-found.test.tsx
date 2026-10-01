import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { NotFoundPage } from "@/pages/not-found";
import { renderWithProviders } from "@/test-utils";

function Destination(): JSX.Element {
  return <output aria-label="Destination">{useLocation().pathname}</output>;
}

describe("NotFoundPage", () => {
  it("provides a page heading and one keyboard-operable recovery control", async () => {
    const { container } = renderWithProviders(<><NotFoundPage /><Destination /></>, { route: "/unavailable-view" });
    const user = userEvent.setup();

    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Return to your workspace" })).toBeInTheDocument();
    expect(container.querySelector("a button, button a")).not.toBeInTheDocument();
    const recover = screen.getByRole("button", { name: "Back to overview" });
    recover.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByLabelText("Destination")).toHaveTextContent(/^\/$/);
  });
});