import { useState } from "react";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/layout/sidebar";
import { navigationFor } from "@/components/layout/navigation";
import { renderWithProviders } from "@/test-utils";

function Host() {
  const [open,setOpen]=useState(false);
  return <><button onClick={()=>setOpen(true)}>Open mobile navigation</button><Sidebar items={navigationFor(()=>true)} workspaceName="Test workspace" collapsed={false} onToggleCollapse={()=>{}} mobileOpen={open} onCloseMobile={()=>setOpen(false)}/></>;
}
describe("Mobile navigation",()=>{
  it("traps focus and returns it to the trigger after Escape",async()=>{
    renderWithProviders(<Host/>);
    const user=userEvent.setup();
    const opener=screen.getByText("Open mobile navigation");
    await user.click(opener);
    const dialog=screen.getByRole("dialog",{name:"Navigation"});
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
    await user.tab({shift:true});
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});

describe("Workspace navigation", () => {
  it("leaves search to the top bar and keeps the expanded copilot entry permission-aware", () => {
    renderWithProviders(<Sidebar items={navigationFor(permission => permission !== "copilot.ask")} workspaceName="Test workspace" collapsed={false} onToggleCollapse={() => {}} mobileOpen={false} onCloseMobile={() => {}} />);
    expect(screen.queryByRole("button", { name: "Search pages and records" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ask EPOS" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open project copilot" })).not.toBeInTheDocument();
  });

  it("preserves the current-page label and collapse action in compact navigation", async () => {
    const toggle = vi.fn();
    renderWithProviders(<Sidebar items={navigationFor(() => true)} workspaceName="Test workspace" collapsed onToggleCollapse={toggle} mobileOpen={false} onCloseMobile={() => {}} />);
    expect(screen.getByRole("link", { name: "Executive summary" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Ask EPOS" })).toHaveAttribute("title", "Ask EPOS");
    expect(screen.queryByRole("button", { name: "Open project copilot" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Expand navigation" }));
    expect(toggle).toHaveBeenCalledOnce();
  });

  it("makes the optional copilot entry a native action", async () => {
    renderWithProviders(<Sidebar items={navigationFor(() => true)} workspaceName="Test workspace" collapsed={false} onToggleCollapse={() => {}} mobileOpen={false} onCloseMobile={() => {}} />);
    const button = screen.getByRole("button", { name: "Open project copilot" });
    expect(button).toHaveAttribute("data-slot", "magic-button");
    await userEvent.click(button);
    expect(screen.getByRole("link", { name: "Ask EPOS" })).toHaveAttribute("aria-current", "page");
  });
});