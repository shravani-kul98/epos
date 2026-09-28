import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createPortal } from "react-dom";
import { ArrowUpRight, CornerDownLeft, FileSearch, Search, X } from "lucide-react";

import { cn } from "@/lib/cn";
import { useWorkspaceSearch } from "@/lib/queries";
import { useModalFocus } from "@/lib/use-modal-focus";
import type { NavigationItem } from "@/components/layout/navigation";
import type { ProjectSummary } from "@/types/api";

interface CommandMenuProps {
  open: boolean;
  onClose: () => void;
  navigation: NavigationItem[];
  projects: ProjectSummary[];
}

interface CommandEntry {
  id: string;
  label: string;
  group: string;
  hint?: string;
  path: string;
}

const LOCAL_LIMIT = 6;
const DEBOUNCE_MS = 200;

/** Delay the request until typing pauses, so a search is one call rather than one per keystroke. */
function useDebounced(value: string, delay: number): string {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);

  return settled;
}

/**
 * Keyboard-first navigation and workspace search. Opened with Ctrl+K. Pages and projects resolve
 * instantly from data already loaded; every other record type is found through the API, so a
 * milestone, risk, requirement, change request or decision is reachable from one place.
 */
export function CommandMenu({ open, onClose, navigation, projects }: CommandMenuProps): JSX.Element | null {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useModalFocus(open, onClose);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const debounced = useDebounced(open ? query : "", DEBOUNCE_MS);
  const results = useWorkspaceSearch(debounced);

  const local = useMemo<CommandEntry[]>(() => {
    const pages: CommandEntry[] = navigation.map((item) => ({
      id: `page-${item.path}`,
      label: item.label,
      group: "Go to",
      path: item.path,
    }));
    const projectEntries: CommandEntry[] = projects.map((project) => ({
      id: `project-${project.project_id}`,
      label: project.project_name,
      group: "Projects",
      hint: `${project.project_id} · ${project.assessment?.is_assessed === false ? "Not yet assessed" : project.health_band}`,
      path: `/projects/${project.project_id}`,
    }));
    return [...pages, ...projectEntries];
  }, [navigation, projects]);

  const matches = useMemo<CommandEntry[]>(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return local.slice(0, 12);

    const nearby = local
      .filter(
        (entry) =>
          entry.label.toLowerCase().includes(needle) ||
          (entry.hint ?? "").toLowerCase().includes(needle),
      )
      .slice(0, LOCAL_LIMIT);

    const seen = new Set(nearby.map((entry) => entry.path));
    const remote: CommandEntry[] = (results.data?.hits ?? [])
      .map((hit) => ({
        id: `${hit.record_type}-${hit.record_id}`,
        label: hit.title,
        group: hit.record_type_label,
        hint: [hit.record_id, hit.status, hit.project_name].filter(Boolean).join(" · "),
        path: hit.path,
      }))
      .filter((entry) => !seen.has(entry.path));

    return [...nearby, ...remote].slice(0, 20);
  }, [local, query, results.data]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      inputRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  if (!open) return null;

  function choose(entry: CommandEntry | undefined): void {
    if (!entry) return;
    navigate(entry.path);
    onClose();
  }

  const needle = query.trim();
  const selectedIndex = Math.min(active, Math.max(0, matches.length - 1));
  const searching = needle.length >= 2 && results.isFetching;
  const omitted = results.data ? results.data.total - results.data.hits.length : 0;

  let lastGroup = "";

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[8dvh] sm:pt-[12dvh]">
      <button type="button" aria-label="Close search" tabIndex={-1} onClick={onClose} className="godui-overlay-scrim absolute inset-0 bg-overlay" />
      <div ref={dialogRef} role="dialog" aria-label="Search workspace" aria-modal="true" tabIndex={-1} className="workspace-command godui-overlay-chrome relative max-h-[80dvh] w-full max-w-2xl overflow-y-auto rounded-overlay border border-line bg-surface shadow-overlay">
        <div className="workspace-command-search flex items-center gap-2">
          <Search aria-hidden="true" className="h-4 w-4 text-ink-secondary" />
          <input
            ref={inputRef}
            data-autofocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing) return;
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive((index) => Math.max(0, Math.min(index + 1, matches.length - 1)));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((index) => Math.max(index - 1, 0));
              } else if (event.key === "Enter") {
                event.preventDefault();
                choose(matches[selectedIndex]);
              }
            }}
            placeholder="Search anything: projects, milestones, risks, requirements, decisions"
            aria-label="Search the workspace"
            className="h-11 min-w-0 flex-1 bg-transparent text-body text-ink outline-none placeholder:text-ink-secondary"
          />
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close workspace search"><X size={16} aria-hidden="true" /></button>
        </div>
        {results.isError ? <p role="status" className="border-b border-line p-3 text-meta text-warn">Record search is unavailable. Page and project shortcuts still work.</p> : null}
        <ul className="workspace-command-results max-h-[55dvh] overflow-y-auto">
          {matches.length === 0 ? (
            <li className="px-3 py-6 text-center text-body text-ink-secondary">
              {searching
                ? "Searching…"
                : needle.length === 1
                  ? "Keep typing to search the workspace."
                  : "No matches"}
            </li>
          ) : (
            matches.map((entry, index) => {
              const showGroup = entry.group !== lastGroup;
              lastGroup = entry.group;
              return (
                <li key={entry.id}>
                  {showGroup ? (
                    <p className="px-3 pb-1 pt-3 text-meta font-medium text-ink-secondary">
                      {entry.group}
                    </p>
                  ) : null}
                  <button
                    type="button"
                    onMouseEnter={() => setActive(index)}
                    onClick={() => choose(entry)}
                    data-active={index === selectedIndex || undefined}
                    className={cn(
                      "workspace-command-entry flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-body",
                      index === selectedIndex ? "bg-accent-tint text-ink" : "text-ink-secondary hover:bg-surface-subtle",
                    )}
                  >
                    <span className="workspace-command-entry-icon" aria-hidden="true">{entry.group === "Go to" ? <ArrowUpRight size={15} /> : <FileSearch size={15} />}</span>
                    <span className="min-w-0 flex-1 break-words">{entry.label}</span>
                    {entry.hint ? (
                      <span className="max-w-[45%] text-right text-meta text-ink-secondary">{entry.hint}</span>
                    ) : null}
                  </button>
                </li>
              );
            })
          )}
        </ul>
        <div className="workspace-command-footer">
          <span><kbd>↑ ↓</kbd>Move <kbd>Enter</kbd>Open <kbd>Esc</kbd>Close</span>
          <span className="flex items-center gap-1"><CornerDownLeft size={12} aria-hidden="true" />Pages, projects and records</span>
        </div>
        {omitted > 0 ? (
          <p className="border-t border-line px-3 py-2 text-meta text-ink-muted">
            Showing the closest matches. {omitted} more record{omitted === 1 ? "" : "s"} also match.
          </p>
        ) : null}
      </div>
    </div>, document.body,
  );
}
