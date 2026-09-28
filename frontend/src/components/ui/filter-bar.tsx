import { useState, type ReactNode } from "react";
import { Check, Link2, SlidersHorizontal, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export function FilterBar({ children, onClear, active = false, description = "Filter this view", shareable = true }: {
  children: ReactNode;
  onClear?: () => void;
  active?: boolean;
  description?: string;
  shareable?: boolean;
}): JSX.Element {
  const [message, setMessage] = useState("");
  const [copied, setCopied] = useState(false);
  async function copyView(): Promise<void> {
    setCopied(false);
    try {
      await navigator.clipboard.writeText(window.location.href);
      setMessage("View link copied.");
      setCopied(true);
    } catch {
      setMessage("Copy the browser address to share these filters.");
    }
  }
  return <section aria-label={description} className="workspace-filter mb-5 rounded-card border border-line bg-surface p-4">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <p className="workspace-filter-heading flex flex-wrap items-center gap-2 font-medium text-ink-secondary"><SlidersHorizontal size={15} aria-hidden="true" />{description}{active ? <span className="workspace-filter-active">Filters applied</span> : null}</p>
      <div className="flex flex-wrap items-center gap-2">
        {active && onClear ? <Button size="sm" variant="ghost" onClick={onClear}><X size={14} aria-hidden="true" />Clear filters</Button> : null}
        {shareable ? <Button size="sm" variant="ghost" onClick={() => void copyView()}>{copied ? <Check size={14} aria-hidden="true" /> : <Link2 size={14} aria-hidden="true" />}Share view</Button> : null}
      </div>
    </div>
    <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-2 xl:grid-cols-4">{children}</div>
    {message ? <p className="mt-3 text-meta text-ink-secondary" role="status">{message}</p> : null}
  </section>;
}