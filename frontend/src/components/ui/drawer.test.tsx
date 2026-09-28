import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Drawer } from "@/components/ui/drawer";

function Host({ dirty = false }: { dirty?: boolean }) {
  const [open, setOpen] = useState(false);
  return <>
    <button onClick={() => setOpen(true)}>Open editor</button>
    <Drawer open={open} onClose={() => setOpen(false)} dirty={dirty} title="Edit record" description="Existing record" footer={(close) => <button onClick={close}>Cancel</button>}>
      <input aria-label="Record title" />
    </Drawer>
  </>;
}

function NestedHost() {
  const [parent, setParent] = useState(false);
  const [child, setChild] = useState(false);
  return <>
    <button onClick={() => setParent(true)}>Open parent</button>
    <Drawer open={parent} onClose={() => setParent(false)} title="Parent">
      <button onClick={() => setChild(true)}>Inspect evidence</button>
      <Drawer open={child} onClose={() => setChild(false)} title="Nested evidence">
        <p>Selected evidence</p>
      </Drawer>
    </Drawer>
  </>;
}

describe("Drawer accessibility", () => {
  it("closes only the top modal and keeps background isolation until the parent closes", async () => {
    const root = document.createElement("div");
    root.id = "root";
    document.body.appendChild(root);
    const { unmount } = render(<NestedHost />, { container: root });
    const user = userEvent.setup();
    await user.click(screen.getByText("Open parent"));
    expect(root.inert).toBe(true);
    await user.click(screen.getByText("Inspect evidence"));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Nested evidence" })).not.toBeInTheDocument();
    expect(screen.getByText("Inspect evidence")).toHaveFocus();
    expect(root.inert).toBe(true);
    await user.keyboard("{Escape}");
    expect(root.inert).toBe(false);
    expect(screen.getByText("Open parent")).toHaveFocus();
    unmount();
    root.remove();
  });
  it("contains keyboard focus, closes with Escape and restores the opener", async () => {
    render(<Host />);
    const user = userEvent.setup();
    const opener = screen.getByRole("button", { name: "Open editor" });
    await user.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Edit record" });
    expect(dialog).toHaveAccessibleDescription("Existing record");
    expect(within(dialog).getByRole("button", { name: "Close" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    await user.tab();
    expect(within(dialog).getByRole("button", { name: "Close" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("keeps dirty input until discard is explicitly confirmed", async () => {
    render(<Host dirty />);
    const user = userEvent.setup();
    await user.click(screen.getByText("Open editor"));
    await user.type(screen.getByLabelText("Record title"), "Unsaved title");
    await user.keyboard("{Escape}");
    expect(screen.getByRole("alert")).toHaveTextContent("Discard unsaved changes?");
    await user.click(screen.getByText("Keep editing"));
    expect(screen.getByLabelText("Record title")).toHaveValue("Unsaved title");
    await user.click(screen.getByText("Cancel"));
    await user.click(screen.getByText("Discard changes"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});