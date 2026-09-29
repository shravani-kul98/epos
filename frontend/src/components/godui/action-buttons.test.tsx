import { createRef, type FormEvent } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MagicButton } from "@/components/godui/magic-button";
import { ProgressFoldButton } from "@/components/godui/progress-fold-button";

describe("GodUI action buttons", () => {
  it("keeps the tactile button native, ref-forwarding and non-submitting by default", async () => {
    const ref = createRef<HTMLButtonElement>();
    const submit = vi.fn((event: FormEvent<HTMLFormElement>) => event.preventDefault());
    const click = vi.fn();
    render(<form onSubmit={submit}><MagicButton ref={ref} onClick={click}>Create project</MagicButton></form>);
    const button = screen.getByRole("button", { name: "Create project" });
    expect(ref.current).toBe(button);
    expect(button).toHaveAttribute("type", "button");
    expect(button).not.toHaveAttribute("data-rainbow");
    await userEvent.click(button);
    expect(click).toHaveBeenCalledOnce();
    expect(submit).not.toHaveBeenCalled();
  });

  it("preserves explicit submit and disabled semantics", async () => {
    const submit = vi.fn((event: FormEvent<HTMLFormElement>) => event.preventDefault());
    const { rerender } = render(<form onSubmit={submit}><MagicButton type="submit">Save</MagicButton></form>);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(submit).toHaveBeenCalledOnce();
    rerender(<form onSubmit={submit}><MagicButton type="submit" disabled>Save</MagicButton></form>);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(submit).toHaveBeenCalledOnce();
  });

  it("composes keyboard handlers and clears the pressed face on blur", () => {
    const down = vi.fn();
    const up = vi.fn();
    const blur = vi.fn();
    render(<MagicButton onKeyDown={down} onKeyUp={up} onBlur={blur}>Open</MagicButton>);
    const button = screen.getByRole("button", { name: "Open" });
    fireEvent.keyDown(button, { key: " " });
    expect(button).toHaveAttribute("data-pressed", "true");
    fireEvent.keyUp(button, { key: " " });
    expect(button).not.toHaveAttribute("data-pressed");
    fireEvent.keyDown(button, { key: "Enter" });
    fireEvent.blur(button);
    expect(button).not.toHaveAttribute("data-pressed");
    expect(down).toHaveBeenCalledTimes(2);
    expect(up).toHaveBeenCalledOnce();
    expect(blur).toHaveBeenCalledOnce();
  });

  it("respects a caller that prevents a keyboard action", () => {
    render(<MagicButton onKeyDown={event => event.preventDefault()}>Open</MagicButton>);
    const button = screen.getByRole("button", { name: "Open" });
    fireEvent.keyDown(button, { key: "Enter" });
    expect(button).not.toHaveAttribute("data-pressed");
  });

  it("blocks duplicate submissions and keeps progress separate from the button name", async () => {
    const ref = createRef<HTMLButtonElement>();
    const submit = vi.fn((event: FormEvent<HTMLFormElement>) => event.preventDefault());
    const { rerender } = render(<form onSubmit={submit}><ProgressFoldButton ref={ref} type="submit">Calculate</ProgressFoldButton></form>);
    const button = screen.getByRole("button", { name: "Calculate" });
    expect(ref.current).toBe(button);
    await userEvent.click(button);
    expect(submit).toHaveBeenCalledOnce();
    rerender(<form onSubmit={submit}><ProgressFoldButton ref={ref} type="submit" status="loading" progressLabel="Calculating comparison">Calculate</ProgressFoldButton></form>);
    expect(button).toHaveAccessibleName("Calculate");
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    const progress = screen.getByRole("progressbar", { name: "Calculating comparison" });
    expect(progress).not.toHaveAttribute("aria-valuenow");
    expect(button).not.toContainElement(progress);
    await userEvent.click(button);
    expect(submit).toHaveBeenCalledOnce();
    rerender(<ProgressFoldButton>Calculate</ProgressFoldButton>);
    expect(screen.getByRole("button", { name: "Calculate" })).toBeEnabled();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it.each([[0, 0], [35, 35], [-10, 0], [110, 100]])("only reports supplied finite progress %s as %s", (progress, expected) => {
    render(<ProgressFoldButton status="loading" progress={progress}>Working</ProgressFoldButton>);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", String(expected));
    expect(screen.getByRole("button")).toHaveAttribute("data-determinate", "true");
  });

  it.each([NaN, Infinity, -Infinity])("does not invent a percentage for invalid progress %s", progress => {
    render(<ProgressFoldButton status="loading" progress={progress}>Working</ProgressFoldButton>);
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
    expect(screen.getByRole("button")).not.toHaveAttribute("data-determinate");
  });

  it("keeps explicitly disabled idle actions disabled", () => {
    render(<ProgressFoldButton disabled progress={50}>Calculate</ProgressFoldButton>);
    expect(screen.getByRole("button")).toBeDisabled();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});
