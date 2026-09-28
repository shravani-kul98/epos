import { createRef, type FormEvent } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/button";
import { Field, TextInput } from "@/components/ui/form";

describe("Shared GodUI adapters", () => {
  it.each(["primary", "secondary", "ghost", "danger"] as const)("keeps %s buttons native and ref-forwarding", variant => {
    const ref = createRef<HTMLButtonElement>();
    const click = vi.fn();
    const { rerender } = render(<Button ref={ref} variant={variant} type="submit" onClick={click} className="justify-start">Continue</Button>);
    const button = screen.getByRole("button", { name: "Continue" });
    expect(button).toHaveAttribute("data-slot", "shimmer-button");
    expect(button).toHaveAttribute("type", "submit");
    expect(button).toHaveClass("justify-start");
    expect(button.querySelector(".godui-shimmer-label")).toHaveClass("contents");
    expect(ref.current).toBe(button);
    fireEvent.click(button);
    expect(click).toHaveBeenCalledOnce();
    rerender(<Button ref={ref} variant={variant} disabled onClick={click}>Continue</Button>);
    fireEvent.click(button);
    expect(click).toHaveBeenCalledOnce();
  });

  it("retains native number bounds, refs, styling, HTML size and field descriptions", () => {
    const ref = createRef<HTMLInputElement>();
    const { container } = render(<Field label="Delay" htmlFor="delay" hint="Choose the requested change.">
      <TextInput ref={ref} type="number" min={0} max={30} step={1} size={8} defaultValue={3} className="pr-12" style={{ textAlign: "right" }} />
    </Field>);
    const input = screen.getByRole("spinbutton", { name: "Delay" });
    expect(ref.current).toBe(input);
    expect(input).toHaveAttribute("min", "0");
    expect(input).toHaveAttribute("max", "30");
    expect(input).toHaveAttribute("step", "1");
    expect(input).toHaveAttribute("size", "8");
    expect(input).toHaveValue(3);
    expect(input).toHaveStyle({ textAlign: "right" });
    expect(input).toHaveClass("pr-12");
    expect(input).toHaveAccessibleDescription("Choose the requested change.");
    expect(container.querySelector('[data-slot="magic-input"]')).toBeInTheDocument();
  });

  it("preserves Enter form submission rather than enabling a value-submit button", async () => {
    const submitted = vi.fn((event: FormEvent<HTMLFormElement>) => event.preventDefault());
    const inputSubmit = vi.fn();
    render(<form onSubmit={submitted}><TextInput aria-label="Name" onSubmit={inputSubmit} /><Button type="submit">Save</Button></form>);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Name" }), "Example{Enter}");
    expect(submitted).toHaveBeenCalledOnce();
    expect(inputSubmit).not.toHaveBeenCalled();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });
});