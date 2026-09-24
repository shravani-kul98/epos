import { useLayoutEffect, useRef } from "react";

const layers: HTMLElement[] = [];
let previousOverflow = "";
let previousInert = false;

function focusableWithin(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(
    'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => element.tabIndex >= 0 && !element.closest('[hidden], [inert]') &&
    getComputedStyle(element).display !== "none" && getComputedStyle(element).visibility !== "hidden");
}

/** Modal layers share a lock so closing a nested panel cannot unlock its parent. */
export function useModalFocus(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useLayoutEffect(() => {
    const node = ref.current;
    if (!open || !node) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const root = document.getElementById("root");
    if (layers.length === 0) {
      previousOverflow = document.body.style.overflow;
      previousInert = root?.inert ?? false;
      document.body.style.overflow = "hidden";
      if (root) root.inert = true;
    }
    layers.push(node);
    (node.querySelector<HTMLElement>('[data-autofocus]') ?? focusableWithin(node)[0] ?? node).focus();

    function onKeyDown(event: KeyboardEvent): void {
      if (layers[layers.length - 1] !== node) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeRef.current();
      } else if (event.key === "Tab" && node) {
        const controls = focusableWithin(node);
        const first = controls[0] ?? node;
        const last = controls[controls.length - 1] ?? node;
        if (event.shiftKey && (document.activeElement === first || !node.contains(document.activeElement))) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !node.contains(document.activeElement))) {
          event.preventDefault();
          first.focus();
        }
      }
    }

    function containFocus(event: FocusEvent): void {
      if (layers[layers.length - 1] === node && node && !node.contains(event.target as Node)) {
        (focusableWithin(node)[0] ?? node).focus();
      }
    }

    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("focusin", containFocus);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("focusin", containFocus);
      layers.splice(layers.indexOf(node), 1);
      if (layers.length === 0) {
        document.body.style.overflow = previousOverflow;
        if (root) root.inert = previousInert;
      }
      if (opener?.isConnected && !opener.closest("[inert]")) opener.focus({ preventScroll: true });
      // The control that opened the panel can be re-rendered away; keep focus in the page.
      else document.getElementById("main")?.focus({ preventScroll: true });
    };
  }, [open]);

  return ref;
}