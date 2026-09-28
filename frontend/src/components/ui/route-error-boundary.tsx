import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

export class RouteErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return <section role="alert" className="mx-auto my-8 max-w-xl rounded-card border border-line bg-surface p-6">
      <h1 className="text-section font-medium">This view could not be opened</h1>
      <p className="mt-2 text-body text-ink-secondary">A new application version or an unavailable connection may have interrupted loading. No records were changed.</p>
      <Button className="mt-4" onClick={() => window.location.reload()}>Reload application</Button>
    </section>;
  }
}