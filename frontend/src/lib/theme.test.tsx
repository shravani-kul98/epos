import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { ThemeProvider, useTheme } from "@/lib/theme";

function Host(){const {theme,toggle}=useTheme();return <button onClick={toggle}>{theme}</button>;}
afterEach(()=>{window.localStorage.clear();document.documentElement.removeAttribute("data-theme");});
describe("Theme preference",()=>{
  it("restores an intentional theme and persists a user change",async()=>{
    window.localStorage.setItem("epos.theme","dark");
    render(<ThemeProvider><Host/></ThemeProvider>);
    expect(document.documentElement).toHaveAttribute("data-theme","dark");
    await userEvent.setup().click(screen.getByRole("button",{name:"dark"}));
    expect(document.documentElement).toHaveAttribute("data-theme","light");
    expect(window.localStorage.getItem("epos.theme")).toBe("light");
  });
});