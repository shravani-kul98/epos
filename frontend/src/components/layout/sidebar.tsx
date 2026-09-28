import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { createPortal } from "react-dom";
import { ArrowUpRight, Layers3, PanelLeftClose, Sparkles, X } from "lucide-react";

import { NAVIGATION_SECTIONS, type NavigationItem } from "@/components/layout/navigation";
import { Button } from "@/components/ui/button";
import { MagicButton } from "@/components/godui/magic-button";
import { PRODUCT_NAME } from "@/config";
import { cn } from "@/lib/cn";
import { useModalFocus } from "@/lib/use-modal-focus";

interface SidebarProps {
  items: NavigationItem[];
  workspaceName: string;
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  /** Kept for callers; search now lives only in the top bar. */
  onOpenSearch?: () => void;
}

function NavigationList({
  items,
  collapsed,
  onNavigate,
  footer,
}: {
  items: NavigationItem[];
  collapsed: boolean;
  onNavigate?: () => void;
  footer?: ReactNode;
}): JSX.Element {
  return (
    <div className={cn("flex-1 overflow-y-auto px-2 pb-4", collapsed && "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden")}>
      {NAVIGATION_SECTIONS.map((section) => {
        const sectionItems = items.filter((item) => item.section === section);
        if (sectionItems.length === 0) return null;
        return (
          <div key={section} className="mb-5">
            {collapsed ? (
              <div aria-hidden="true" className="mx-2 mb-2 border-t border-nav-border" />
            ) : (
              <p className="workspace-nav-section px-3 pb-2 text-meta font-medium text-nav-text">
                {section}
              </p>
            )}
            <ul className="space-y-0.5">
              {sectionItems.map((item) => (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    end={item.end ?? false}
                    onClick={onNavigate}
                    title={collapsed ? item.label : undefined}
                    className={({ isActive }) =>
                      cn(
                        "workspace-nav-link relative flex min-h-10 items-center gap-3 rounded-control px-3 py-2 text-body transition-colors",
                        collapsed && "justify-center",
                        isActive
                          ? "bg-nav-active font-medium text-nav-strong before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:rounded-full before:bg-nav-marker"
                          : "text-nav-text hover:bg-nav-hover hover:text-nav-strong",
                      )
                    }
                  >
                    <span className="workspace-nav-icon" aria-hidden="true"><item.icon className="h-4 w-4 shrink-0" /></span>
                    {collapsed ? (
                      <span className="sr-only">{item.label}</span>
                    ) : (
                      <span className="truncate">{item.label}</span>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {footer}
    </div>
  );
}

export function Sidebar({
  items,
  workspaceName,
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
}: SidebarProps): JSX.Element {
  const mobileRef = useModalFocus(mobileOpen, onCloseMobile);
  const navigate = useNavigate();
  return (
    <>
      <nav
        aria-label="Primary"
        data-print-hide
        data-collapsed={collapsed}
        className={cn(
          "workspace-nav hidden shrink-0 flex-col border-r border-nav-border bg-nav text-nav-text transition-[width] duration-base lg:flex",
          collapsed ? "w-sidebar-compact" : "w-sidebar",
        )}
      >
        <div className={cn("mb-3 flex h-topbar shrink-0 items-center gap-3 px-4", collapsed && "justify-center px-0")}>
          <span
            aria-hidden="true"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-control bg-accent text-body font-semibold text-ink-onaccent"
          >
            <Layers3 size={21} strokeWidth={1.6} />
          </span>
          {collapsed ? null : (
            <div className="min-w-0 leading-tight">
              <p className="text-body font-semibold text-nav-strong">{PRODUCT_NAME}</p>
              <p className="truncate text-meta text-nav-text">{workspaceName}</p>
            </div>
          )}
        </div>

        <NavigationList
          items={items}
          collapsed={collapsed}
          footer={!collapsed && items.some(item => item.path === "/ask") ? <div className="workspace-copilot-entry">
            <p><Sparkles size={15} aria-hidden="true" />A little more perspective</p>
            <span>Ask about the work. Keep the evidence.</span>
            <MagicButton variant="secondary" size="sm" onClick={() => navigate("/ask")} aria-label="Open project copilot">Open copilot <ArrowUpRight size={14} aria-hidden="true" /></MagicButton>
          </div> : null}
        />
        <Button
          variant="ghost"
          onClick={onToggleCollapse}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          aria-expanded={!collapsed}
          className="flex min-h-12 items-center justify-start gap-2 rounded-none border-t border-nav-border px-4 py-3 text-meta text-nav-text hover:bg-nav-hover hover:text-nav-strong"
        >
          <PanelLeftClose
            aria-hidden="true"
            className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")}
          />
          {collapsed ? null : "Collapse"}
        </Button>
      </nav>

      {mobileOpen ? createPortal(
        <div className="fixed inset-0 z-50">
          <button
            type="button"
            aria-label="Close navigation"
            tabIndex={-1}
            onClick={onCloseMobile}
            className="godui-overlay-scrim absolute inset-0 bg-overlay"
          />
          <div ref={mobileRef} role="dialog" aria-modal="true" aria-label="Navigation" tabIndex={-1} className="relative h-dvh w-[min(320px,calc(100vw-48px))]">
          <nav
            aria-label="Primary"
            className="flex h-full flex-col bg-nav text-nav-text shadow-overlay"
          >
            <div className="flex h-14 items-center justify-between px-4">
              <div className="flex items-center gap-2.5">
                <span
                  aria-hidden="true"
                  className="flex h-8 w-8 items-center justify-center rounded-control bg-accent text-body font-semibold text-ink-onaccent"
                >
                  <Layers3 size={21} strokeWidth={1.6} />
                </span>
                <div className="leading-tight">
                  <p className="text-body font-semibold text-nav-strong">{PRODUCT_NAME}</p>
                  <p className="text-meta text-nav-text">{workspaceName}</p>
                </div>
              </div>
              <Button
                variant="ghost"
                onClick={onCloseMobile}
                aria-label="Close navigation"
                className="icon-button text-nav-text hover:bg-nav-hover hover:text-nav-strong"
              >
                <X aria-hidden="true" className="h-4 w-4" />
              </Button>
            </div>
            <NavigationList items={items} collapsed={false} onNavigate={onCloseMobile} />
          </nav>
          </div>
        </div>, document.body,
      ) : null}
    </>
  );
}
