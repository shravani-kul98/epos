import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PageContext, PageHeader } from "@/components/ui/page-header";
import { TermHelp } from "@/components/ui/term-help";

describe("TermHelp", () => {
  it("uses a focusable native summary and opens without hover", async () => {
    render(<TermHelp term="health" />);
    const user = userEvent.setup();
    const summary = screen.getByText("About health");
    const details = summary.closest("details");
    const definition = screen.getByText(/How the recorded work compares/);
    expect(summary.tagName).toBe("SUMMARY");
    expect(details).not.toHaveAttribute("open");
    expect(definition).not.toBeVisible();
    await user.tab();
    expect(summary).toHaveFocus();
    await user.click(summary);
    expect(details).toHaveAttribute("open");
    expect(definition).toBeVisible();
    expect(definition).toHaveTextContent("No colour guarantees delivery or sets a response deadline");
    await user.click(summary);
    expect(details).not.toHaveAttribute("open");
  });

  it("can be opened and closed by touch", async () => {
    render(<TermHelp term="confidence" />);
    const user = userEvent.setup();
    const summary = screen.getByText("About data confidence");
    await user.pointer([{ keys: "[TouchA]", target: summary }, { keys: "[/TouchA]" }]);
    expect(summary.closest("details")).toHaveAttribute("open");
    expect(screen.getByText(/How recently records were updated/)).toBeVisible();
    expect(screen.getByText(/How recently records were updated/)).toHaveTextContent("not a probability of success or a guarantee that the data is correct");
    await user.pointer([{ keys: "[TouchA]", target: summary }, { keys: "[/TouchA]" }]);
    expect(summary.closest("details")).not.toHaveAttribute("open");
  });

  it.each([
    ["gateReadiness", "About gate readiness", "human approval is still required"],
    ["traceState", "About trace state", "linked tests and evidence"],
    ["assumption", "About assumption", "needs validating with evidence and an accountable owner"],
    ["analysisDate", "About analysis date", "does not restore a historical snapshot"],
  ] as const)("explains %s without treating it as an automatic decision", async (term, label, definition) => {
    render(<TermHelp term={term} />);
    const summary = screen.getByText(label);
    await userEvent.setup().click(summary);
    expect(summary.closest("details")).toHaveTextContent(definition);
  });
});

describe("PageHeader analysis-date help", () => {
  it("explains the supplied context date without calculating a replacement", async () => {
    render(<PageContext.Provider value={{ scope: "Portfolio", asOfDate: "2026-09-22" }}><PageHeader title="Projects" /></PageContext.Provider>);
    expect(screen.getByText("22 Sep 2026")).toHaveAttribute("datetime", "2026-09-22");
    await userEvent.setup().click(screen.getByText("About analysis date"));
    expect(screen.getByText(/Defaults to today in UTC/)).toBeVisible();
    expect(screen.getByText(/Defaults to today in UTC/)).toHaveTextContent("An explicit as-of date evaluates the current records against that date");
  });

  it("keeps an explicit as-of date ahead of the context date", () => {
    render(<PageContext.Provider value={{ asOfDate: "2026-09-22" }}><PageHeader title="Projects" asOfDate="2026-08-25" /></PageContext.Provider>);
    expect(screen.getByText("25 Aug 2026")).toHaveAttribute("datetime", "2026-08-25");
    expect(screen.queryByText("22 Sep 2026")).not.toBeInTheDocument();
  });

  it("does not introduce a date or date help when none is supplied", () => {
    render(<PageHeader title="Projects" scope="Workspace" />);
    expect(screen.queryByText("About analysis date")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument();
  });
});