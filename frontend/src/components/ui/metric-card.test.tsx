import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { MetricCard } from "@/components/ui/metric-card";

describe("Spotlight metric cards", () => {
  it("leaves supplied values unchanged and static metrics out of the tab order", () => {
    const { container } = render(<MetricCard label="Health" value="59.3" unit="/ 100" caption="Recorded result" />);
    expect(screen.getByText("59.3")).toHaveAttribute("data-numeric");
    expect(screen.getByText("Recorded result")).toBeInTheDocument();
    expect(container.querySelector('[data-slot="spotlight-card"]')).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(container.querySelector("[tabindex]")).not.toBeInTheDocument();
  });

  it("retains a real route link and keeps footer controls outside it", async () => {
    const inspect = vi.fn();
    const open = vi.fn();
    render(<MemoryRouter><MetricCard label="Projects" value={10} href="/portfolio" onClick={open} footer={<button onClick={inspect}>Inspect sources</button>} /></MemoryRouter>);
    const link = screen.getByRole("link", { name: "Projects 10" });
    const footer = screen.getByRole("button", { name: "Inspect sources" });
    expect(link).toHaveAttribute("href", "/portfolio");
    expect(link).not.toHaveAttribute("aria-pressed");
    expect(link).not.toContainElement(footer);
    await userEvent.click(footer);
    expect(inspect).toHaveBeenCalledOnce();
    expect(open).not.toHaveBeenCalled();
  });

  it("keeps filtering keyboard-operable with an explicit pressed state", async () => {
    const click = vi.fn();
    render(<MetricCard label="Red band" value={2} onClick={click} active tone="critical" />);
    const button = screen.getByRole("button", { name: "Red band 2" });
    expect(button).toHaveAttribute("type", "button");
    expect(button).toHaveAttribute("aria-pressed", "true");
    button.focus();
    await userEvent.keyboard("{Enter}");
    expect(click).toHaveBeenCalledOnce();
    fireEvent.pointerMove(button, { clientX: 10, clientY: 10 });
    expect(button).toHaveFocus();
  });

  it("does not turn unavailable data into a zero", () => {
    render(<MetricCard label="Open issues" value="—" caption="Records unavailable" size="compact" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
