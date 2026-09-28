import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RecordReference } from "@/components/ui/record-reference";
import { DataTable } from "@/components/ui/data-table";

describe("Record references", () => {
  it("keeps references available without treating expansion as opening the row editor", async () => {
    const open = vi.fn();
    render(<DataTable rows={[{ id: "T-very-long-preserved-record" }]} rowKey={row => row.id} columns={[{ key: "name", header: "Task", cell: row => <RecordReference references={[row.id]} /> }]} onRowClick={open} />);
    const summary = screen.getByText("Record references");
    expect(summary.closest("details")).not.toHaveAttribute("open");
    await userEvent.setup().click(summary);
    expect(summary.closest("details")).toHaveAttribute("open");
    expect(open).not.toHaveBeenCalled();
    expect(screen.getByText("T-very-long-preserved-record")).toBeVisible();
  });
});
