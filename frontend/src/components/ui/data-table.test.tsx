import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DataTable } from "@/components/ui/data-table";

const rows = Array.from({ length: 18 }, (_, index) => ({ id: `ROW-${index}`, name: `Record ${index}`, value: index }));
const columns = [
  { key: "name", header: "Record", value: (row: typeof rows[number]) => row.name, cell: (row: typeof rows[number]) => row.name },
  { key: "value", header: "Value", value: (row: typeof rows[number]) => row.value, cell: (row: typeof rows[number]) => row.value },
];

describe("DataTable", () => {
  it("pages without losing records and exposes sort state", async () => {
    render(<DataTable rows={rows} columns={columns} rowKey={r => r.id} label="Delivery" initialSortKey="value" />);
    const user = userEvent.setup();
    expect(screen.getByRole("columnheader", { name: /Value/ })).toHaveAttribute("aria-sort", "ascending");
    expect(screen.queryByText("Record 17")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Record 17")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sort by Value" }));
    expect(screen.getByRole("columnheader", { name: /Value/ })).toHaveAttribute("aria-sort", "descending");
    expect(within(screen.getAllByRole("row")[1]!).getByText("Record 17")).toBeInTheDocument();
  });

  it("offers a named keyboard action without hijacking nested links", async () => {
    const open = vi.fn();
    render(<DataTable rows={rows.slice(0, 1)} columns={columns} rowKey={r => r.id} onRowClick={open} />);
    const user = userEvent.setup();
    screen.getByRole("button", { name: "Open ROW-0" }).focus();
    await user.keyboard("{Enter}");
    expect(open).toHaveBeenCalledTimes(1);
    expect(open).toHaveBeenCalledWith(rows[0]);
  });

  it("clears an empty search and distinguishes unavailable data from zero records", async () => {
    const { rerender } = render(<DataTable rows={rows} columns={columns} rowKey={r => r.id} />);
    const user = userEvent.setup();
    await user.type(screen.getByRole("searchbox"), "no match");
    expect(screen.getByText("No matches")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Clear filter" })[0]!);
    expect(screen.getByText("Record 0")).toBeInTheDocument();
    rerender(<DataTable rows={undefined} columns={columns} rowKey={r => r.id} error={new Error("offline")} />);
    expect(screen.getByText("Records unavailable")).toBeInTheDocument();
    expect(screen.queryByText("0 records")).not.toBeInTheDocument();
  });

  it("changes density without changing the current page, order or records", async () => {
    const { container } = render(<DataTable rows={rows} columns={columns} rowKey={row => row.id} label="Delivery" initialSortKey="value" />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Next page" }));
    const records = within(screen.getByRole("table")).getAllByRole("row").map(row => row.textContent);
    await user.click(screen.getByRole("button", { name: "Compact rows" }));
    expect(screen.getByRole("group", { name: "Delivery row density" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compact rows" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Comfortable rows" })).toHaveAttribute("aria-pressed", "false");
    expect(container.querySelector(".workspace-table")).toHaveAttribute("data-density", "compact");
    expect(within(screen.getByRole("table")).getAllByRole("row").map(row => row.textContent)).toEqual(records);
    expect(screen.getByText("16–18 of 18")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Comfortable rows" }));
    expect(container.querySelector(".workspace-table")).toHaveAttribute("data-density", "comfortable");
  });

  it("remembers the chosen density for the same table on a later visit", async () => {
    window.localStorage.removeItem("epos.table-density.Remembered");
    const first = render(<DataTable rows={rows} columns={columns} rowKey={row => row.id} label="Remembered" />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Compact rows" }));
    first.unmount();
    const { container } = render(<DataTable rows={rows} columns={columns} rowKey={row => row.id} label="Remembered" />);
    expect(container.querySelector(".workspace-table")).toHaveAttribute("data-density", "compact");
    expect(screen.getByRole("button", { name: "Compact rows" })).toHaveAttribute("aria-pressed", "true");
    window.localStorage.removeItem("epos.table-density.Remembered");
  });

  it("keeps the native search and does not hijack nested controls or unavailable rows", async () => {
    const open = vi.fn();
    const inspect = vi.fn();
    const editableColumns = [...columns, { key: "action", header: "Action", cell: (row: typeof rows[number]) => <button onClick={() => inspect(row)}>Inspect {row.id}</button> }];
    const { container } = render(<DataTable rows={rows.slice(0, 2)} columns={editableColumns} rowKey={row => row.id} onRowClick={open} canOpenRow={row => row.id === "ROW-0"} />);
    const user = userEvent.setup();
    expect(container.querySelector('[data-slot="magic-input"]')).toContainElement(screen.getByRole("searchbox"));
    await user.click(screen.getByRole("button", { name: "Inspect ROW-0" }));
    expect(inspect).toHaveBeenCalledOnce();
    expect(open).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Open ROW-1" })).not.toBeInTheDocument();
    await user.click(screen.getByText("Record 1"));
    expect(open).not.toHaveBeenCalled();
    await user.click(screen.getByText("Record 0"));
    expect(open).toHaveBeenCalledOnce();
    expect(open).toHaveBeenCalledWith(rows[0]);
  });
});