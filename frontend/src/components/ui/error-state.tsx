import { CircleAlert, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}

/** Turn any thrown value into a sentence a user can act on. */
export function describeError(error: unknown): { title: string; message: string; recoverable: boolean } {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return {
        title: "Can't reach EPOS",
        message: "Check your network connection, then try again. If it keeps happening, tell your workspace administrator.",
        recoverable: true,
      };
    }
    if (error.status === 403) {
      return {
        title: "Not available to your role",
        message: error.message,
        recoverable: false,
      };
    }
    if (error.status === 404) {
      return { title: "Not found", message: error.message, recoverable: false };
    }
    return { title: "Request failed", message: error.message, recoverable: true };
  }
  return {
    title: "Something went wrong",
    message: "EPOS could not display this section. Try again.",
    recoverable: true,
  };
}

export function ErrorState({ error, onRetry, className }: ErrorStateProps): JSX.Element {
  const { title, message, recoverable } = describeError(error);
  return (
    <div className={cn("px-6 py-10 text-center", className)} role="alert">
      <span className="workspace-error-symbol" aria-hidden="true"><CircleAlert size={22} /></span>
      <h3 className="text-section font-semibold text-ink">{title}</h3>
      <p className="mx-auto mt-1 max-w-md text-body text-ink-secondary">{message}</p>
      {recoverable && onRetry ? (
        <Button variant="secondary" className="mt-4" onClick={onRetry}>
          <RotateCw size={14} aria-hidden="true" />
          Try again
        </Button>
      ) : null}
    </div>
  );
}
