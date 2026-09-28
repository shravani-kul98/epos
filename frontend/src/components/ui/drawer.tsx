import { useEffect, useId, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { useModalFocus } from "@/lib/use-modal-focus";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode | ((close: () => void) => ReactNode);
  width?: string;
  dirty?: boolean;
  busy?: boolean;
}

/** A right-hand panel for detail and editing, so context on the page behind is never lost. */
export function Drawer({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = "max-w-xl",
  dirty = false,
  busy = false,
}: DrawerProps): JSX.Element | null {
  const titleId = useId();
  const descriptionId = useId();
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  function requestClose(): void {
    if (busy) return;
    if (dirty) setConfirmDiscard(true);
    else onClose();
  }
  const ref = useModalFocus(open, requestClose);

  useEffect(() => {
    if (!open) setConfirmDiscard(false);
  }, [open]);

  useEffect(() => {
    if (!open || !dirty) return;
    function beforeUnload(event: BeforeUnloadEvent): void {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [open, dirty]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close panel"
        tabIndex={-1}
        onClick={requestClose}
        className="godui-overlay-scrim absolute inset-0 bg-overlay"
      />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        aria-busy={busy}
        tabIndex={-1}
        className={cn("workspace-drawer godui-overlay-chrome relative flex h-dvh w-full min-w-0 flex-col bg-surface shadow-overlay sm:border-l sm:border-line", width)}
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-section font-semibold text-ink">{title}</h2>
            {description ? <p id={descriptionId} className="mt-1 text-meta text-ink-secondary">{description}</p> : null}
          </div>
          <button
            type="button"
            onClick={requestClose}
            disabled={busy}
            aria-label="Close"
            className="icon-button"
          >
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
          {confirmDiscard ? (
            <div role="alert" className="mb-4 rounded-card border border-warn bg-warn-tint p-4">
              <p className="font-medium">Discard unsaved changes?</p>
              <p className="mt-1 text-body text-ink-secondary">Your changes have not been saved.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button autoFocus onClick={() => setConfirmDiscard(false)}>Keep editing</Button>
                <Button variant="danger" onClick={onClose}>Discard changes</Button>
              </div>
            </div>
          ) : null}
          {children}
        </div>
        {footer ? (
          <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-surface px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            {typeof footer === "function" ? footer(requestClose) : footer}
          </footer>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
