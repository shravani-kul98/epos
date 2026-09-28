import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { AlignJustify, ArrowDown, ArrowUp, ArrowUpRight, ChevronLeft, ChevronRight, ChevronsUpDown, List, Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { MagicInput } from "@/components/godui/magic-input";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SkeletonTable } from "@/components/ui/loading-skeleton";
import { cn } from "@/lib/cn";

export interface Column<Row> {
  key: string;
  header: string;
  /** Rendered cell content. */
  cell: (row: Row) => ReactNode;
  /** Comparable value used for sorting and search. Omit to make the column inert. */
  value?: (row: Row) => string | number;
  align?: "left" | "right";
  width?: string;
}

interface DataTableProps<Row> {
  rows: Row[] | undefined;
  columns: Column<Row>[];
  rowKey: (row: Row) => string;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  onRowClick?: (row: Row) => void;
  canOpenRow?: (row: Row) => boolean;
  rowActionLabel?: (row: Row) => string;
  label?: string;
  pageSize?: number;
  filterValue?: string;
  onFilterChange?: (value: string) => void;
  searchPlaceholder?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  toolbar?: ReactNode;
  initialSortKey?: string;
  initialSortDirection?: "asc" | "desc";
  className?: string;
}

function compare(a: string | number, b: string | number): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

type Density = "comfortable" | "compact";

function densityKey(tableLabel: string): string {
  return `epos.table-density.${tableLabel}`;
}

/** A row density chosen earlier for this table, so a preference survives a return visit. */
function storedDensity(tableLabel: string): Density {
  try {
    return window.localStorage.getItem(densityKey(tableLabel)) === "compact" ? "compact" : "comfortable";
  } catch {
    return "comfortable";
  }
}

const NARROW_QUERY = "(max-width: 639px)";

/** Phones get stacked rows; wide columns there would hide behind a sideways scroll. */
function useNarrowScreen(): boolean {
  const [narrow, setNarrow] = useState(() => typeof window.matchMedia === "function" && window.matchMedia(NARROW_QUERY).matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const query = window.matchMedia(NARROW_QUERY);
    const update = (): void => setNarrow(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return narrow;
}

/**
 * The single table used across EPOS. It owns sorting, filtering and the loading, empty and error
 * states so every list in the product behaves identically.
 */
export function DataTable<Row>({
  rows,
  columns,
  rowKey,
  isLoading = false,
  error,
  onRetry,
  onRowClick,
  canOpenRow,
  rowActionLabel,
  label,
  pageSize = 15,
  filterValue,
  onFilterChange,
  searchPlaceholder = "Filter",
  emptyTitle = "Nothing to show",
  emptyDescription = "No records match the current view.",
  emptyAction,
  toolbar,
  initialSortKey,
  initialSortDirection = "asc",
  className,
}: DataTableProps<Row>): JSX.Element {
  const [localQuery, setLocalQuery] = useState("");
  const [page, setPage] = useState(0);
  const narrow = useNarrowScreen();
  const tableLabel = label ?? (searchPlaceholder.replace(/^Filter\s*/i, "").trim() || "Records");
  const [density, setDensityState] = useState<Density>(() => storedDensity(tableLabel));
  function setDensity(value: Density): void {
    setDensityState(value);
    try {
      window.localStorage.setItem(densityKey(tableLabel), value);
    } catch {
      // A blocked storage API only loses the preference, never the table.
    }
  }
  const query = filterValue ?? localQuery;
  function setQuery(value: string): void {
    setPage(0);
    setLocalQuery(value);
    onFilterChange?.(value);
  }
  const [sortKey, setSortKey] = useState<string | undefined>(initialSortKey);
  const [direction, setDirection] = useState<"asc" | "desc">(initialSortDirection);

  const visible = useMemo(() => {
    if (!rows) return [];
    const searchable = columns.filter((column) => column.value);
    const needle = query.trim().toLowerCase();
    const filtered = needle
      ? rows.filter((row) =>
          searchable.some((column) => String(column.value?.(row) ?? "").toLowerCase().includes(needle)),
        )
      : rows.slice();

    const column = columns.find((item) => item.key === sortKey);
    if (column?.value) {
      const accessor = column.value;
      filtered.sort((left, right) => {
        const result = compare(accessor(left), accessor(right));
        return direction === "asc" ? result : -result;
      });
    }
    return filtered;
  }, [rows, columns, query, sortKey, direction]);

  function toggleSort(key: string): void {
    setPage(0);
    if (sortKey === key) {
      setDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setDirection("asc");
  }

  const showToolbar = Boolean(toolbar) || columns.some((column) => column.value);
  const size = Math.max(1, pageSize);
  const pageCount = Math.max(1, Math.ceil(visible.length / size));
  const currentPage = Math.min(page, pageCount - 1);
  const shown = visible.slice(currentPage * size, (currentPage + 1) * size);

  return (
    <div className={cn("workspace-table card min-w-0 overflow-hidden", className)} aria-busy={isLoading} data-density={density}>
      {showToolbar ? (
        <div className="workspace-table-toolbar flex flex-wrap items-center gap-2 border-b border-line px-3 py-2.5">
          <div className="relative min-w-0 basis-48 flex-1">
            <MagicInput
              size="sm" rainbow={false} leadingIcon={<Search size={15} />}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchPlaceholder}
              aria-label={searchPlaceholder}
              inputClassName="pr-10"
            />
            {query ? <button type="button" aria-label="Clear filter" onClick={() => setQuery("")} className="icon-button absolute right-0 top-0 z-10"><X aria-hidden="true" size={14} /></button> : null}
          </div>
          {toolbar}
          <span className="ml-auto text-meta text-ink-secondary" data-numeric aria-live="polite" aria-atomic="true">
            {isLoading ? "Loading records" : error ? "Records unavailable" : `${visible.length} ${visible.length === 1 ? "record" : "records"}`}
          </span>
          <div className="workspace-density" role="group" aria-label={`${tableLabel} row density`}>
            <Button variant="ghost" size="sm" aria-label="Comfortable rows" aria-pressed={density === "comfortable"} onClick={() => setDensity("comfortable")}><List size={15} aria-hidden="true" /></Button>
            <Button variant="ghost" size="sm" aria-label="Compact rows" aria-pressed={density === "compact"} onClick={() => setDensity("compact")}><AlignJustify size={15} aria-hidden="true" /></Button>
          </div>
        </div>
      ) : null}

      {error ? (
        <ErrorState error={error} {...(onRetry ? { onRetry } : {})} />
      ) : isLoading ? (
        <SkeletonTable />
      ) : visible.length === 0 ? (
        <EmptyState
          title={rows && rows.length > 0 ? "No matches" : emptyTitle}
          description={
            rows && rows.length > 0
              ? "No records match the current filter. Clear it to see everything again."
              : emptyDescription
          }
          headingLevel={2}
          action={rows && rows.length > 0 ? <Button onClick={() => setQuery("")}>Clear filter</Button> : emptyAction}
        />
      ) : narrow ? (
        <ul aria-label={`${tableLabel} records`} className="divide-y divide-line">
          {shown.map((row) => {
            const [lead, ...rest] = columns;
            const openable = onRowClick && (!canOpenRow || canOpenRow(row));
            return (
              <li key={rowKey(row)} className="space-y-2 px-3 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1 text-body text-ink">{lead ? lead.cell(row) : null}</div>
                  {openable ? (
                    <button type="button" className="icon-button shrink-0" aria-label={rowActionLabel?.(row) ?? `Open ${rowKey(row)}`} onClick={() => onRowClick?.(row)}>
                      <ArrowUpRight size={16} aria-hidden="true" />
                    </button>
                  ) : null}
                </div>
                {rest.length ? (
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
                    {rest.map((column) => (
                      <div key={column.key} className="min-w-0">
                        <dt className="text-meta text-ink-secondary">{column.header}</dt>
                        <dd className="min-w-0 text-body text-ink">{column.cell(row)}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <div role="region" aria-label={`${tableLabel} table`} tabIndex={0} className="overflow-x-auto">
          <table className="w-full border-collapse text-table">
            <caption className="sr-only">{tableLabel}</caption>
            <thead className="bg-surface-subtle">
              <tr className="border-b border-line bg-surface-subtle">
                {columns.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={column.value ? (sortKey === column.key ? (direction === "asc" ? "ascending" : "descending") : "none") : undefined}
                    style={column.width ? { width: column.width } : undefined}
                    className={cn(
                      "px-3 py-2.5 text-meta font-medium text-ink-secondary",
                      column.align === "right" ? "text-right" : "text-left",
                    )}
                  >
                    {column.value ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column.key)}
                        className={cn(
                          "inline-flex min-h-6 items-center gap-1 hover:text-ink",
                          column.align === "right" && "flex-row-reverse",
                        )}
                        aria-label={`Sort by ${column.header}`}
                      >
                        {column.header}
                        {sortKey === column.key ? (
                          direction === "asc" ? (
                            <ArrowUp aria-hidden="true" className="h-3 w-3" />
                          ) : (
                            <ArrowDown aria-hidden="true" className="h-3 w-3" />
                          )
                        ) : (
                          <ChevronsUpDown aria-hidden="true" className="h-3 w-3 opacity-40" />
                        )}
                      </button>
                    ) : (
                      column.header
                    )}
                  </th>
                ))}
                {onRowClick ? <th scope="col" className="w-12"><span className="sr-only">Open record</span></th> : null}
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={onRowClick && (!canOpenRow || canOpenRow(row)) ? (event) => {
                    if (!(event.target as HTMLElement).closest("a, button, input, select, textarea, details, summary")) onRowClick(row);
                  } : undefined}
                  className={cn(
                    "border-b border-line transition-colors last:border-0 hover:bg-surface-subtle focus-within:bg-accent-tint",
                    onRowClick && (!canOpenRow || canOpenRow(row)) && "cursor-pointer",
                  )}
                >
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={cn(
                        "px-3 py-2.5 align-middle text-ink",
                        column.align === "right" && "text-right tabular-nums",
                      )}
                    >
                      {column.cell(row)}
                    </td>
                  ))}
                  {onRowClick ? <td className="px-2">
                    {!canOpenRow || canOpenRow(row) ? (
                      <button type="button" className="icon-button" aria-label={rowActionLabel?.(row) ?? `Open ${rowKey(row)}`} onClick={() => onRowClick(row)}>
                        <ArrowUpRight size={16} aria-hidden="true" />
                      </button>
                    ) : null}
                  </td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!isLoading && !error && visible.length > size ? (
        <nav aria-label={`${tableLabel} pagination`} className="workspace-table-pagination flex flex-wrap items-center justify-between gap-2 border-t border-line px-3 py-2">
          <span className="text-meta text-ink-secondary" data-numeric>
            {currentPage * size + 1}–{Math.min((currentPage + 1) * size, visible.length)} of {visible.length}
          </span>
          <div className="flex items-center gap-2">
            <Button size="sm" aria-label="Previous page" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={16} aria-hidden="true" /></Button>
            <span className="text-meta tabular-nums">Page {currentPage + 1} of {pageCount}</span>
            <Button size="sm" aria-label="Next page" disabled={currentPage + 1 >= pageCount} onClick={() => setPage(currentPage + 1)}><ChevronRight size={16} aria-hidden="true" /></Button>
          </div>
        </nav>
      ) : null}
    </div>
  );
}
