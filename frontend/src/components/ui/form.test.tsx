import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Field, Select, TextArea, TextInput } from "@/components/ui/form";

describe("Field semantics", () => {
  it("connects hints and errors while preserving input value", () => {
    const { rerender } = render(<Field htmlFor="owner" label="Owner" hint="Use a recorded owner."><TextInput defaultValue="Synthetic Owner" /></Field>);
    expect(screen.getByLabelText("Owner")).toHaveAccessibleDescription("Use a recorded owner.");
    rerender(<Field htmlFor="owner" label="Owner" hint="Use a recorded owner." error="Select an owner."><TextInput defaultValue="Synthetic Owner" /></Field>);
    expect(screen.getByLabelText("Owner")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Owner")).toHaveAccessibleDescription("Use a recorded owner. Select an owner.");
    expect(screen.getByLabelText("Owner")).toHaveValue("Synthetic Owner");
  });

  it("applies the same semantics to selectors and text areas", () => {
    render(<>
      <Field htmlFor="phase" label="Phase" error="Choose a phase."><Select><option>Execution</option></Select></Field>
      <Field htmlFor="rationale" label="Rationale" hint="Explain the decision."><TextArea required /></Field>
    </>);
    expect(screen.getByLabelText("Phase")).toHaveAccessibleDescription("Choose a phase.");
    expect(screen.getByLabelText("Rationale")).toBeRequired();
  });
});