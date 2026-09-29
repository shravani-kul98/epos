import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MagicTab } from "./magic-tab";

const items = [
  { value: "health", label: "Health", id: "health-tab", controls: "health-panel" },
  { value: "unavailable", label: "Unavailable", disabled: true },
  { value: "risk", label: "Risk", id: "risk-tab", controls: "risk-panel" },
];

describe("GodUI tab keyboard contract", () => {
  it("moves focus past disabled items without selecting until activation", async () => {
    const changed = vi.fn();
    render(<MagicTab items={items} onValueChange={changed} aria-label="Capabilities" />);
    const user = userEvent.setup();
    await user.tab();
    const health = screen.getByRole("tab", { name: "Health" });
    const risk = screen.getByRole("tab", { name: "Risk" });
    expect(health).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(risk).toHaveFocus();
    expect(health).toHaveAttribute("aria-selected", "true");
    expect(changed).not.toHaveBeenCalled();
    await user.keyboard("{Enter}");
    expect(changed).toHaveBeenCalledOnce();
    expect(changed).toHaveBeenCalledWith("risk");
    expect(risk).toHaveAttribute("aria-selected", "true");
    expect(risk).toHaveAttribute("aria-controls", "risk-panel");
    await user.keyboard("{ArrowRight}");
    expect(health).toHaveFocus();
  });

  it("keeps controlled selection external and supports Home, End and Space", async () => {
    const changed = vi.fn();
    const { rerender } = render(<MagicTab items={items} value="health" onValueChange={changed} />);
    const user = userEvent.setup();
    await user.tab();
    await user.keyboard("{End} ");
    expect(changed).toHaveBeenCalledWith("risk");
    expect(screen.getByRole("tab", { name: "Health" })).toHaveAttribute("aria-selected", "true");
    rerender(<MagicTab items={items} value="risk" onValueChange={changed} />);
    expect(screen.getByRole("tab", { name: "Risk" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Health" })).toHaveFocus();
  });

  it("respects prevented keyboard events and never activates disabled items", () => {
    const changed = vi.fn();
    render(<MagicTab items={items} onValueChange={changed} onKeyDown={event => event.preventDefault()} />);
    const health = screen.getByRole("tab", { name: "Health" });
    health.focus();
    fireEvent.keyDown(health, { key: "ArrowRight" });
    expect(health).toHaveFocus();
    fireEvent.click(screen.getByRole("tab", { name: "Unavailable" }));
    expect(changed).not.toHaveBeenCalled();
  });

  it("resets the tab stop to the selected item when leaving the group", async () => {
    render(<><MagicTab items={items} /><button type="button">Continue</button></>);
    const user = userEvent.setup();
    await user.tab();
    await user.keyboard("{End}");
    await user.tab();
    expect(screen.getByRole("button", { name: "Continue" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole("tab", { name: "Health" })).toHaveFocus();
  });
});