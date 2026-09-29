// Adapted from GodUI's MIT-licensed magic-tab registry item; see LICENSE.txt.
import { forwardRef, useCallback, useEffect, useRef, useState, type HTMLAttributes, type MutableRefObject, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface MagicTabItem {
  value: string;
  label: ReactNode;
  disabled?: boolean;
  id?: string;
  controls?: string;
}

export interface MagicTabProps extends Omit<HTMLAttributes<HTMLDivElement>, "onChange"> {
  items: MagicTabItem[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  variant?: "default" | "secondary";
  size?: "sm" | "md" | "lg";
  rainbow?: boolean;
}

export const MagicTab = forwardRef<HTMLDivElement, MagicTabProps>(function MagicTab(
  { items, value, defaultValue, onValueChange, variant = "default", size = "md", rainbow = false,
    className, onKeyDown, onBlur, ...props }, ref,
) {
  const [internalValue, setInternalValue] = useState(() => defaultValue ?? items.find(item => !item.disabled)?.value);
  const [focusValue, setFocusValue] = useState<string>();
  const selectedValue = value ?? internalValue;
  const rovingValue = focusValue ?? selectedValue;
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const setRefs = useCallback((node: HTMLDivElement | null) => {
    rootRef.current = node;
    if (typeof ref === "function") ref(node);
    else if (ref) (ref as MutableRefObject<HTMLDivElement | null>).current = node;
  }, [ref]);

  useEffect(() => {
    const root = rootRef.current;
    if (!rainbow || !root || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry) return;
      root.style.setProperty("--godui-tab-play-state", entry.isIntersecting ? "running" : "paused");
    }, { rootMargin: "128px" });
    observer.observe(root);
    return () => observer.disconnect();
  }, [rainbow]);

  function select(next: string): void {
    if (value === undefined) setInternalValue(next);
    if (next !== selectedValue) onValueChange?.(next);
  }

  function moveFocus(next: string): void {
    setFocusValue(next);
    tabRefs.current[items.findIndex(item => item.value === next)]?.focus();
  }

  return (
    <div {...props} ref={setRefs} role="tablist" aria-orientation="horizontal"
      data-slot="magic-tab" data-variant={variant} data-size={size} data-rainbow={rainbow || undefined}
      className={cn("godui-tabs", className)}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget)) setFocusValue(undefined);
        onBlur?.(event);
      }}
      onKeyDown={event => {
        onKeyDown?.(event);
        if (event.defaultPrevented) return;
        const enabled = items.filter(item => !item.disabled);
        if (!enabled.length) return;
        const index = Math.max(0, enabled.findIndex(item => item.value === rovingValue));
        let next: MagicTabItem | undefined;
        switch (event.key) {
          case "ArrowRight": case "ArrowDown": next = enabled[(index + 1) % enabled.length]; break;
          case "ArrowLeft": case "ArrowUp": next = enabled[(index - 1 + enabled.length) % enabled.length]; break;
          case "Home": next = enabled[0]; break;
          case "End": next = enabled[enabled.length - 1]; break;
          case "Enter": case " ":
            if (rovingValue && enabled.some(item => item.value === rovingValue)) {
              event.preventDefault();
              select(rovingValue);
            }
            return;
          default: return;
        }
        if (next) { event.preventDefault(); moveFocus(next.value); }
      }}>
      {items.map((item, index) => (
        <button key={item.value} ref={node => { tabRefs.current[index] = node; }}
          id={item.id} type="button" role="tab" aria-selected={item.value === selectedValue}
          aria-controls={item.controls} disabled={item.disabled} tabIndex={item.value === rovingValue ? 0 : -1}
          className="godui-tab" onClick={() => { setFocusValue(item.value); select(item.value); }}>
          <span className="godui-tab-shadow" aria-hidden="true" />
          <span className="godui-tab-edge" aria-hidden="true" />
          <span className="godui-tab-front">{item.label}</span>
        </button>
      ))}
    </div>
  );
});